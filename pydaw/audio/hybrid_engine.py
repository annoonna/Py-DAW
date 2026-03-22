"""Hybrid Audio Engine (v0.0.20.14) — C-Speed Audio, Python GUI.

v0.0.20.14 Changes:
- Per-track volume/pan/mute/solo via ParamRingBuffer + TrackParamState
- render_for_jack() fully integrated into JACK process callback
- HybridSounddeviceCallback: drop-in replacement for arrangement playback
- Track index registry for mapping track_id → track_idx

Architecture:
    ┌──────────────────────────────────────────────────────────┐
    │                      GUI THREAD (PyQt6)                  │
    │  ┌────────────┐  ┌─────────┐  ┌──────────┐  ┌────────┐ │
    │  │ Arranger   │  │ Mixer   │  │Transport │  │Sampler │ │
    │  └─────┬──────┘  └────┬────┘  └────┬─────┘  └───┬────┘ │
    │        │              │            │             │       │
    │        ▼              ▼            ▼             ▼       │
    │  ┌─────────────────────────────────────────────────────┐ │
    │  │    ParamRingBuffer (lock-free, per-track + master)   │ │
    │  └─────────────────────────┬───────────────────────────┘ │
    └────────────────────────────┼─────────────────────────────┘
                                 │ (zero-lock boundary)
    ┌────────────────────────────┼─────────────────────────────┐
    │                    AUDIO THREAD                          │
    │  ┌─────────────────────────▼───────────────────────────┐ │
    │  │          HybridAudioCallback                         │ │
    │  │  • drain_into(TrackParamState) → per-track mix       │ │
    │  │  • per-track vol/pan/mute/solo with IIR smoothing    │ │
    │  │  • render arrangement (numpy C-speed)                │ │
    │  │  • mix pull sources (Sampler, FluidSynth)            │ │
    │  │  • master vol/pan (smoothed, click-free)             │ │
    │  │  • soft limiter + metering ring                      │ │
    │  └──────────────────────────────────────────────────────┘ │
    └──────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import math
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import numpy as np
except Exception:
    np = None

from .ring_buffer import (
    ParamRingBuffer, AudioRingBuffer, TrackMeterRing, TrackParamState,
    PARAM_MASTER_VOL, PARAM_MASTER_PAN,
    PARAM_TRACK_BASE, PARAM_TRACK_STRIDE,
    TRACK_VOL, TRACK_PAN, TRACK_MUTE, TRACK_SOLO,
    track_param_id, decode_track_param, MAX_TRACKS,
)
from .rt_params import RTParamStore

from pydaw.utils.logging_setup import get_logger

log = get_logger(__name__)

_HALF_PI = 1.5707963267948966


def _pan_gains(gain: float, pan: float) -> Tuple[float, float]:
    """Equal-power pan law."""
    pan = max(-1.0, min(1.0, float(pan)))
    x = (pan + 1.0) * 0.5
    return (math.cos(x * _HALF_PI) * gain,
            math.sin(x * _HALF_PI) * gain)


class HybridAudioCallback:
    """Zero-lock audio callback for sounddevice/JACK.

    All state is read from pre-cached local variables or lock-free rings.
    No Python locks, no allocations, no exceptions in the hot path.

    v0.0.20.14: Per-track volume/pan/mute/solo via TrackParamState.
    """

    __slots__ = (
        # Pre-allocated buffers
        "_mix_buf", "_block_buf",
        # Per-track scratch buffers (v0.0.20.25)
        "_track_bufs", "_active_tracks_buf",
        # Parameters (local copies, updated from ring)
        "_master_vol", "_master_pan",
        "_master_vol_smooth", "_master_pan_smooth",
        "_smooth_coeff",
        # Per-track state (v0.0.20.14)
        "_track_state",
        # Track index registry: track_id -> track_idx
        "_track_index_map",
        # Ring buffers
        "_param_ring", "_meter_ring",
        # Per-track meter rings
        "_track_meters",
        # Arrangement state (atomic reference swap)
        "_arrangement_state",
        # Pull sources (atomic list swap)
        "_pull_sources",
        # Transport ref
        "_transport_ref",
        # Playhead for silence mode
        "_silence_playhead",
        # RT params ref (optional, for backward compat)
        "_rt_params",
        # Audio-FX chain map (track_id -> ChainFx)
        "_track_audio_fx_map", "_master_track_id",
        # Config
        "_sr",
        # v0.0.20.41: Direct peaks + track index reverse map
        "_direct_peaks_ref", "_track_index_to_id",
        # v0.0.20.42: Sampler registry for real-time MIDI→Sampler triggering
        "_sampler_registry",
        # v0.0.20.80: Instrument bypass set (track_ids with instrument_enabled=False)
        "_bypassed_track_ids",
        # v0.0.20.357: Group bus routing (child_track_idx -> group_track_idx)
        "_group_bus_map",       # dict: child_idx -> group_idx
        "_group_track_idxs",    # set of group track indices
        "_group_bus_id_map",    # dict: child_track_id -> group_track_idx (for pull sources)
        # v0.0.20.518: Send-FX bus routing (Bitwig-style)
        "_send_bus_map",        # dict: source_track_idx -> list of (fx_track_idx, amount, pre_fader)
        "_fx_track_idxs",       # set of FX track indices
        "_send_bus_id_map",     # dict: source_track_id -> list of (fx_track_idx, amount, pre_fader)
        # v0.0.20.641: Sidechain routing (AP5 Phase 5B)
        "_sidechain_map",       # dict: dest_track_idx -> source_track_idx
        "_sidechain_id_map",    # dict: dest_track_id -> source_track_id
        "_sidechain_bufs",      # dict: source_track_idx -> numpy buffer (pre-fader copy)
        # v0.0.20.641: Channel config (AP5 Phase 5C)
        "_channel_config_map",  # dict: track_idx -> "mono"|"stereo"
        # v0.0.20.653: Multi-Output Plugin Routing (AP5 Phase 5C wiring)
        "_plugin_output_map",   # dict: parent_track_id -> {output_idx: child_track_id}
    )

    def __init__(self, param_ring: ParamRingBuffer,
                 meter_ring: Optional[AudioRingBuffer] = None,
                 rt_params: Optional[RTParamStore] = None,
                 sr: int = 48000):
        if np is not None:
            self._mix_buf = np.zeros((8192, 2), dtype=np.float32)
            self._block_buf = np.zeros((8192, 2), dtype=np.float32)
            # v0.0.20.25: Per-track scratch buffers (zero-alloc render_track)
            self._track_bufs = np.zeros((MAX_TRACKS, 8192, 2), dtype=np.float32)
        else:
            self._mix_buf = None
            self._block_buf = None
            self._track_bufs = None

        self._param_ring = param_ring
        self._meter_ring = meter_ring
        self._rt_params = rt_params
        # Audio-FX: compiled ChainFx objects (swapped from GUI thread)
        self._track_audio_fx_map = {}
        self._master_track_id = ""
        self._sr = int(sr)

        # Master parameters
        self._master_vol = 0.8
        self._master_pan = 0.0
        self._master_vol_smooth = 0.8
        self._master_pan_smooth = 0.0
        self._smooth_coeff = 0.0

        # v0.0.20.14: Per-track parameter state
        self._track_state = TrackParamState()
        self._track_index_map: Dict[str, int] = {}
        self._track_meters: Dict[int, TrackMeterRing] = {}
        self._active_tracks_buf: List[int] = []  # reused list for RT path

        # Atomic references (swapped from main thread)
        self._arrangement_state = None
        self._pull_sources: List[Any] = []
        self._transport_ref = None
        self._silence_playhead = 0

        # v0.0.20.41: Reference to AudioEngine._direct_peaks for reliable metering
        self._direct_peaks_ref: Optional[dict] = None
        self._track_index_to_id: Dict[int, str] = {}  # reverse map for peak writing

        # v0.0.20.42: Sampler registry for real-time MIDI→Sampler triggering
        self._sampler_registry: Any = None

        # v0.0.20.80: Set of track_ids whose instruments are bypassed (Power OFF)
        self._bypassed_track_ids: set = set()

        # v0.0.20.357: Group bus routing
        self._group_bus_map: Dict[int, int] = {}        # child_idx -> group_idx
        self._group_track_idxs: set = set()              # group track indices
        self._group_bus_id_map: Dict[str, int] = {}      # child_tid -> group_idx

        # v0.0.20.518: Send-FX bus routing (Bitwig-style)
        self._send_bus_map: Dict[int, list] = {}         # source_idx -> [(fx_idx, amount, pre_fader), ...]
        self._fx_track_idxs: set = set()                 # FX track indices
        self._send_bus_id_map: Dict[str, list] = {}      # source_tid -> [(fx_idx, amount, pre_fader), ...]

        # v0.0.20.641: Sidechain routing (AP5 Phase 5B)
        self._sidechain_map: Dict[int, int] = {}         # dest_track_idx -> source_track_idx
        self._sidechain_id_map: Dict[str, str] = {}      # dest_track_id -> source_track_id
        self._sidechain_bufs: Dict[int, Any] = {}        # source_track_idx -> pre-fader buffer snapshot

        # v0.0.20.641: Channel config (AP5 Phase 5C)
        self._channel_config_map: Dict[int, str] = {}    # track_idx -> "mono"|"stereo"

        # v0.0.20.653: Multi-Output Plugin Routing wiring
        # parent_track_id -> {output_idx: child_track_id}
        # Output 0 always goes to parent track (implicit, not stored here).
        # Only output indices >= 1 appear in this map.
        self._plugin_output_map: Dict[str, Dict[int, str]] = {}

    def set_arrangement_state(self, state: Any) -> None:
        """Set arrangement state (main thread). Atomic reference swap."""
        self._arrangement_state = state

    def set_pull_sources(self, sources: List[Any]) -> None:
        """Set pull source list (main thread). Atomic reference swap."""
        self._pull_sources = list(sources) if sources else []

    def set_transport_ref(self, transport: Any) -> None:
        self._transport_ref = transport

    def set_track_index_map(self, mapping: Dict[str, int]) -> None:
        """Set track_id → track_idx mapping (main thread)."""

        # v0.0.20.81 regression fix:
        # This mapping is REQUIRED for per-track gain/pan + VU metering + direct peaks.
        try:
            self._track_index_map = dict(mapping) if mapping else {}
            # v0.0.20.41: Reverse map for direct peak writing
            self._track_index_to_id = {v: k for k, v in (mapping or {}).items()}
        except Exception:
            # Keep safe defaults — callback must never crash due to mapping issues
            self._track_index_map = {}
            self._track_index_to_id = {}

    def set_bypassed_track_ids(self, bypassed: set) -> None:
        """Set of track_ids with instrument_enabled=False (main thread). Atomic swap."""
        try:
            self._bypassed_track_ids = set(bypassed) if bypassed else set()
        except Exception:
            self._bypassed_track_ids = set()

    def set_track_audio_fx_map(self, fx_map: Dict[str, Any]) -> None:
        """Set compiled per-track Audio-FX map (main thread).

        Atomic reference swap — callback reads this dict without locks.
        """
        try:
            self._track_audio_fx_map = dict(fx_map) if fx_map else {}
        except Exception:
            self._track_audio_fx_map = {}

    def set_group_bus_map(self, child_to_group: Dict[int, int],
                          group_idxs: set,
                          child_id_to_group: Dict[str, int]) -> None:
        """Set group-bus routing maps (main thread). Atomic reference swap.

        v0.0.20.357: Enables real group-bus summing in the audio callback.
        child_to_group: child_track_idx -> group_track_idx
        group_idxs: set of group track indices
        child_id_to_group: child_track_id -> group_track_idx (for pull sources)
        """
        try:
            self._group_bus_map = dict(child_to_group) if child_to_group else {}
            self._group_track_idxs = set(group_idxs) if group_idxs else set()
            self._group_bus_id_map = dict(child_id_to_group) if child_id_to_group else {}
        except Exception:
            self._group_bus_map = {}
            self._group_track_idxs = set()
            self._group_bus_id_map = {}

    def set_master_track_id(self, track_id: str) -> None:
        try:
            self._master_track_id = str(track_id or "")
        except Exception:
            self._master_track_id = ""

    def set_send_bus_map(self, send_map: Dict[int, list],
                         fx_idxs: set,
                         send_id_map: Dict[str, list]) -> None:
        """Set send-FX routing maps (main thread). Atomic reference swap.

        v0.0.20.518: Enables Bitwig-style send-FX bus summing in the audio callback.
        send_map: source_track_idx -> [(fx_track_idx, amount, pre_fader), ...]
        fx_idxs: set of FX track indices (they receive send audio, not arrangement clips)
        send_id_map: source_track_id -> [(fx_track_idx, amount, pre_fader), ...]
        """
        try:
            self._send_bus_map = dict(send_map) if send_map else {}
            self._fx_track_idxs = set(fx_idxs) if fx_idxs else set()
            self._send_bus_id_map = dict(send_id_map) if send_id_map else {}
        except Exception:
            self._send_bus_map = {}
            self._fx_track_idxs = set()
            self._send_bus_id_map = {}

    def set_sidechain_map(self, sc_map: Dict[int, int],
                          sc_id_map: Dict[str, str]) -> None:
        """Set sidechain routing maps (main thread). Atomic reference swap.

        v0.0.20.641 (AP5 Phase 5B): Track-to-track sidechain routing.
        sc_map: dest_track_idx -> source_track_idx
        sc_id_map: dest_track_id -> source_track_id
        """
        try:
            self._sidechain_map = dict(sc_map) if sc_map else {}
            self._sidechain_id_map = dict(sc_id_map) if sc_id_map else {}
        except Exception:
            self._sidechain_map = {}
            self._sidechain_id_map = {}

    def set_channel_config_map(self, config_map: Dict[int, str]) -> None:
        """Set per-track channel configuration (main thread). Atomic swap.

        v0.0.20.641 (AP5 Phase 5C): Mono/Stereo per track.
        config_map: track_idx -> "mono"|"stereo"
        Mono tracks get L+R summed to mono before vol/pan application.
        """
        try:
            self._channel_config_map = dict(config_map) if config_map else {}
        except Exception:
            self._channel_config_map = {}

    def set_plugin_output_map(self, output_map: Dict[str, Dict[int, str]]) -> None:
        """Set multi-output plugin routing (main thread). Atomic reference swap.

        v0.0.20.653 (AP5 Phase 5C wiring): Multi-output plugin routing in audio callback.
        output_map: parent_track_id -> {output_idx: child_track_id}
        Output 0 always goes to the parent track (implicit).
        Only output indices >= 1 are stored here.
        """
        try:
            self._plugin_output_map = dict(output_map) if output_map else {}
        except Exception:
            self._plugin_output_map = {}

    def get_track_meter(self, track_idx: int) -> TrackMeterRing:
        """Get or create per-track meter ring."""
        if track_idx not in self._track_meters:
            self._track_meters[track_idx] = TrackMeterRing()
        return self._track_meters[track_idx]

    def __call__(self, outdata, frames: int, time_info, status) -> None:
        """The actual audio callback. Called by sounddevice.

        ZERO LOCKS. ZERO ALLOCATIONS. ZERO EXCEPTIONS (caught).
        """
        try:
            self._process(outdata, int(frames))
        except Exception:
            try:
                outdata.fill(0)
            except Exception:
                pass

    def _process(self, outdata, frames: int) -> None:
        """Inner processing — separated for profiling."""
        if np is None or self._mix_buf is None:
            outdata.fill(0)
            return

        # 0. Compute smoothing coefficient if needed
        if self._smooth_coeff == 0.0:
            tau = 5.0 * float(self._sr) / 1000.0  # 5ms
            self._smooth_coeff = 1.0 - math.exp(-float(frames) / max(1.0, tau))

        # 1. Drain parameter ring (lock-free) — track params go to TrackParamState
        ring = self._param_ring
        ts = self._track_state
        if ring is not None:
            for pid, val in ring.drain_into(ts):
                if pid == PARAM_MASTER_VOL:
                    self._master_vol = val
                elif pid == PARAM_MASTER_PAN:
                    self._master_pan = val

        # 2. Smooth master + track parameters (single-pole IIR)
        coeff = self._smooth_coeff
        self._master_vol_smooth += coeff * (self._master_vol - self._master_vol_smooth)
        self._master_pan_smooth += coeff * (self._master_pan - self._master_pan_smooth)
        ts.advance_smoothing(coeff)

        # 3. Advance RT params if present (backward compat)
        rt = self._rt_params
        if rt is not None:
            try:
                rt.advance(frames, self._sr)
            except Exception:
                pass

        # 4. Zero the mix buffer slice
        mix = self._mix_buf[:frames]
        mix.fill(0.0)

        # 5. Transport playhead sync (start of block)
        st = self._arrangement_state
        transport = self._transport_ref
        if transport is not None:
            try:
                ph = int(st.playhead) if st is not None else int(self._silence_playhead)
                transport._set_external_playhead_samples(ph, float(self._sr))
            except Exception:
                pass

        # 6. Arrangement render (per-track mix: TrackParamState + TrackMeterRing)
        if st is not None:
            try:
                if (np is not None and hasattr(st, "get_active_tracks")
                        and hasattr(st, "render_track") and hasattr(st, "advance")
                        and self._track_bufs is not None):
                    tracks = st.get_active_tracks(frames, out=self._active_tracks_buf)
                    ts = self._track_state

                    # v0.0.20.357: Group bus routing
                    gbm = self._group_bus_map       # child_idx -> group_idx
                    gti = self._group_track_idxs     # set of group track indices

                    # v0.0.20.518: Send-FX bus routing
                    sbm = self._send_bus_map         # source_idx -> [(fx_idx, amount, pre_fader)]
                    fti = self._fx_track_idxs        # set of FX track indices

                    # v0.0.20.641: Sidechain routing (AP5 Phase 5B)
                    scm = self._sidechain_map        # dest_track_idx -> source_track_idx

                    # v0.0.20.641: Channel config (AP5 Phase 5C)
                    ccm = self._channel_config_map   # track_idx -> "mono"|"stereo"

                    # Zero group bus buffers BEFORE child tracks render into them
                    if gti:
                        for _gidx in gti:
                            if 0 <= _gidx < MAX_TRACKS:
                                self._track_bufs[int(_gidx)][:frames].fill(0.0)

                    # Zero FX bus buffers BEFORE sends accumulate into them
                    if fti:
                        for _fidx in fti:
                            if 0 <= _fidx < MAX_TRACKS:
                                self._track_bufs[int(_fidx)][:frames].fill(0.0)

                    for track_idx in tracks:
                        if track_idx < 0 or track_idx >= MAX_TRACKS:
                            continue

                        # Skip group tracks here — they have no clips; processed below
                        if track_idx in gti:
                            continue

                        # v0.0.20.518: Skip FX tracks — they receive only sends; processed below
                        if track_idx in fti:
                            continue

                        vol, pan, audible = ts.get_track_gain(int(track_idx))
                        if not audible:
                            continue

                        tb = self._track_bufs[int(track_idx)]
                        st.render_track(int(track_idx), frames, out=tb)

                        # Audio-FX chain (pre-fader, pre-meter)
                        try:
                            tid = self._track_index_to_id.get(int(track_idx))
                            if tid is not None and self._track_audio_fx_map:
                                fx = self._track_audio_fx_map.get(str(tid))
                                if fx is not None:
                                    # v0.0.20.641: Set sidechain buffer if routed (AP5 Phase 5B)
                                    if scm:
                                        _sc_src = scm.get(int(track_idx))
                                        if _sc_src is not None and 0 <= _sc_src < MAX_TRACKS:
                                            try:
                                                fx.set_sidechain_buffer(self._track_bufs[int(_sc_src)][:frames])
                                            except Exception:
                                                pass
                                        else:
                                            try:
                                                fx.set_sidechain_buffer(None)
                                            except Exception:
                                                pass
                                    fx.process_inplace(tb, frames, self._sr)
                        except Exception:
                            pass

                        # v0.0.20.518: Pre-fader sends (copy raw FX-processed audio to FX bus)
                        if sbm:
                            _sends = sbm.get(int(track_idx))
                            if _sends:
                                for _sfx_idx, _samt, _pre in _sends:
                                    if _pre and 0 <= _sfx_idx < MAX_TRACKS and _samt > 0.0:
                                        try:
                                            self._track_bufs[int(_sfx_idx)][:frames] += tb[:frames] * float(_samt)
                                        except Exception:
                                            pass

                        # v0.0.20.641: Mono summing (AP5 Phase 5C)
                        if ccm and ccm.get(int(track_idx)) == "mono":
                            try:
                                mono = (tb[:frames, 0] + tb[:frames, 1]) * 0.5
                                tb[:frames, 0] = mono
                                tb[:frames, 1] = mono
                            except Exception:
                                pass

                        gl, gr = _pan_gains(vol, pan)

                        # VU metering (peak + decay), lock-free
                        meter = self.get_track_meter(int(track_idx))
                        meter.update_from_block(tb[:frames], gl, gr)

                        # v0.0.20.41: Write direct peaks for reliable mixer VU
                        dp = self._direct_peaks_ref
                        if dp is not None:
                            try:
                                tid = self._track_index_to_id.get(int(track_idx))
                                if tid is not None:
                                    pk_l = float(np.max(np.abs(tb[:frames, 0]))) * abs(gl)
                                    pk_r = float(np.max(np.abs(tb[:frames, 1]))) * abs(gr)
                                    old = dp.get(tid, (0.0, 0.0))
                                    dp[tid] = (max(old[0], pk_l), max(old[1], pk_r))
                            except Exception:
                                pass

                        # Apply vol/pan in-place
                        tb[:frames, 0] *= float(gl)
                        tb[:frames, 1] *= float(gr)

                        # v0.0.20.518: Post-fader sends (copy vol/pan-applied audio to FX bus)
                        if sbm:
                            _sends_post = sbm.get(int(track_idx))
                            if _sends_post:
                                for _sfx_idx, _samt, _pre in _sends_post:
                                    if not _pre and 0 <= _sfx_idx < MAX_TRACKS and _samt > 0.0:
                                        try:
                                            self._track_bufs[int(_sfx_idx)][:frames] += tb[:frames] * float(_samt)
                                        except Exception:
                                            pass

                        # v0.0.20.357: Route to group bus or directly to master
                        _group_idx = gbm.get(int(track_idx)) if gbm else None
                        if _group_idx is not None and 0 <= _group_idx < MAX_TRACKS:
                            self._track_bufs[int(_group_idx)][:frames] += tb[:frames]
                        else:
                            mix[:frames] += tb[:frames]

                    # v0.0.20.357: Process group buses (FX + vol/pan + mix to master)
                    if gti:
                        for _gidx in gti:
                            if _gidx < 0 or _gidx >= MAX_TRACKS:
                                continue
                            gb = self._track_bufs[int(_gidx)]

                            # Group Audio-FX chain
                            try:
                                _gtid = self._track_index_to_id.get(int(_gidx))
                                if _gtid is not None and self._track_audio_fx_map:
                                    _gfx = self._track_audio_fx_map.get(str(_gtid))
                                    if _gfx is not None:
                                        # v0.0.20.641: Sidechain for group (AP5 Phase 5B)
                                        if scm:
                                            _gsc = scm.get(int(_gidx))
                                            if _gsc is not None and 0 <= _gsc < MAX_TRACKS:
                                                try:
                                                    _gfx.set_sidechain_buffer(self._track_bufs[int(_gsc)][:frames])
                                                except Exception:
                                                    pass
                                            else:
                                                try:
                                                    _gfx.set_sidechain_buffer(None)
                                                except Exception:
                                                    pass
                                        _gfx.process_inplace(gb, frames, self._sr)
                            except Exception:
                                pass

                            # Group vol/pan/mute/solo
                            _gvol, _gpan, _gaudible = ts.get_track_gain(int(_gidx))
                            if not _gaudible:
                                continue
                            _ggl, _ggr = _pan_gains(_gvol, _gpan)

                            # Group metering
                            try:
                                _gm = self.get_track_meter(int(_gidx))
                                _gm.update_from_block(gb[:frames], _ggl, _ggr)
                            except Exception:
                                pass

                            # Group direct peaks
                            _gdp = self._direct_peaks_ref
                            if _gdp is not None:
                                try:
                                    _gtid2 = self._track_index_to_id.get(int(_gidx))
                                    if _gtid2 is not None:
                                        _gpkl = float(np.max(np.abs(gb[:frames, 0]))) * abs(_ggl)
                                        _gpkr = float(np.max(np.abs(gb[:frames, 1]))) * abs(_ggr)
                                        _gold = _gdp.get(_gtid2, (0.0, 0.0))
                                        _gdp[_gtid2] = (max(_gold[0], _gpkl), max(_gold[1], _gpkr))
                                except Exception:
                                    pass

                            # Apply group vol/pan and mix into master
                            gb[:frames, 0] *= float(_ggl)
                            gb[:frames, 1] *= float(_ggr)
                            mix[:frames] += gb[:frames]

                    # v0.0.20.518: Process FX buses (receive sends, apply FX chain + vol/pan, mix to master)
                    # Processed AFTER groups so group sends also accumulate into FX buses.
                    if fti:
                        for _fidx in fti:
                            if _fidx < 0 or _fidx >= MAX_TRACKS:
                                continue
                            fb = self._track_bufs[int(_fidx)]

                            # FX-Track Audio-FX chain (the actual return effect: reverb, delay, etc.)
                            try:
                                _ftid = self._track_index_to_id.get(int(_fidx))
                                if _ftid is not None and self._track_audio_fx_map:
                                    _ffx = self._track_audio_fx_map.get(str(_ftid))
                                    if _ffx is not None:
                                        # v0.0.20.641: Sidechain for FX bus (AP5 Phase 5B)
                                        if scm:
                                            _fsc = scm.get(int(_fidx))
                                            if _fsc is not None and 0 <= _fsc < MAX_TRACKS:
                                                try:
                                                    _ffx.set_sidechain_buffer(self._track_bufs[int(_fsc)][:frames])
                                                except Exception:
                                                    pass
                                            else:
                                                try:
                                                    _ffx.set_sidechain_buffer(None)
                                                except Exception:
                                                    pass
                                        _ffx.process_inplace(fb, frames, self._sr)
                            except Exception:
                                pass

                            # FX-Track vol/pan/mute/solo
                            _fvol, _fpan, _faudible = ts.get_track_gain(int(_fidx))
                            if not _faudible:
                                continue
                            _fgl, _fgr = _pan_gains(_fvol, _fpan)

                            # FX-Track metering
                            try:
                                _fm = self.get_track_meter(int(_fidx))
                                _fm.update_from_block(fb[:frames], _fgl, _fgr)
                            except Exception:
                                pass

                            # FX-Track direct peaks
                            _fdp = self._direct_peaks_ref
                            if _fdp is not None:
                                try:
                                    _ftid2 = self._track_index_to_id.get(int(_fidx))
                                    if _ftid2 is not None:
                                        _fpkl = float(np.max(np.abs(fb[:frames, 0]))) * abs(_fgl)
                                        _fpkr = float(np.max(np.abs(fb[:frames, 1]))) * abs(_fgr)
                                        _fold = _fdp.get(_ftid2, (0.0, 0.0))
                                        _fdp[_ftid2] = (max(_fold[0], _fpkl), max(_fold[1], _fpkr))
                                except Exception:
                                    pass

                            # Apply FX-track vol/pan and mix into master
                            fb[:frames, 0] *= float(_fgl)
                            fb[:frames, 1] *= float(_fgr)
                            mix[:frames] += fb[:frames]

                    # Advance playhead ONCE for the whole block
                    st.advance(frames)

                else:
                    # Fallback: legacy full-mix render
                    buf = st.render(frames)
                    if buf is not None:
                        mix[:buf.shape[0]] += buf[:frames]
            except Exception:
                pass
        else:
            try:
                if transport is not None and bool(getattr(transport, "playing", False)):
                    self._silence_playhead += frames
            except Exception:
                pass

        # 7. Process real-time MIDI events → Sampler (v0.0.20.42)
        # MUST come BEFORE pull sources so sampler receives note_on before pull()
        if st is not None and self._sampler_registry is not None:
            bypassed = self._bypassed_track_ids
            try:
                midi_evts = st.get_pending_midi_events(frames)
                for evt in midi_evts:
                    try:
                        # v0.0.20.80: Skip MIDI for bypassed instruments
                        if str(evt.track_id) in bypassed:
                            continue
                        if evt.is_note_on:
                            self._sampler_registry.note_on(
                                str(evt.track_id),
                                int(evt.pitch),
                                int(evt.velocity),
                                pitch_offset_semitones=float(getattr(evt, "pitch_offset_semitones", 0.0) or 0.0),
                                micropitch_curve=list(getattr(evt, "micropitch_curve", None) or []),
                                note_duration_samples=int(getattr(evt, "note_duration_samples", 0) or 0))
                        else:
                            self._sampler_registry.note_off(str(evt.track_id), pitch=int(evt.pitch))
                    except Exception:
                        pass
            except Exception:
                pass

        # 8. Pull sources (Sampler/Drum/SF2/etc.) WITH per-track gain/pan + metering
        # Mirrors the per-track arrangement mixing path.
        ts_pull = self._track_state
        bypassed_pull = self._bypassed_track_ids
        tmp = self._block_buf[:frames] if self._block_buf is not None else None
        for fn in self._pull_sources:
            try:
                # v0.0.20.80: Check instrument bypass before pulling audio
                tid_attr = getattr(fn, "_pydaw_track_id", None)
                tid_pre = tid_attr() if callable(tid_attr) else tid_attr
                tid_pre = str(tid_pre) if tid_pre not in (None, "", "None") else ""
                if tid_pre and tid_pre in bypassed_pull:
                    continue

                b = fn(frames, self._sr)
                if b is None:
                    continue

                b2 = b[:frames, :2]

                tid = tid_pre  # reuse already-resolved track_id

                if tid:
                    idx = self._track_index_map.get(tid)
                    if idx is not None:
                        vol, pan, audible = ts_pull.get_track_gain(int(idx))
                        if not audible:
                            continue
                        gl, gr = _pan_gains(vol, pan)

                        # Audio-FX chain (pre-fader, pre-meter)
                        src = b2
                        tmp_view = tmp[:frames, :2] if tmp is not None else None
                        fx = None
                        try:
                            if self._track_audio_fx_map:
                                fx = self._track_audio_fx_map.get(tid)
                        except Exception:
                            fx = None
                        if fx is not None:
                            try:
                                if tmp_view is not None:
                                    np.copyto(tmp_view, b2, casting='unsafe')
                                    src = tmp_view
                                fx.process_inplace(src, frames, self._sr)
                            except Exception:
                                pass

                        # Track metering + direct peaks
                        try:
                            meter = self.get_track_meter(int(idx))
                            meter.update_from_block(src, float(gl), float(gr))
                        except Exception:
                            pass
                        dp = self._direct_peaks_ref
                        if dp is not None:
                            try:
                                pk_l = float(np.max(np.abs(src[:, 0]))) * abs(gl)
                                pk_r = float(np.max(np.abs(src[:, 1]))) * abs(gr)
                                old = dp.get(tid, (0.0, 0.0))
                                dp[tid] = (max(old[0], pk_l), max(old[1], pk_r))
                            except Exception:
                                pass

                        # Apply vol/pan then mix
                        # v0.0.20.357: Route to group bus if child of a group
                        _pull_gidx = self._group_bus_id_map.get(tid) if self._group_bus_id_map else None
                        _pull_dest = self._track_bufs[int(_pull_gidx)][:frames, :2] if (_pull_gidx is not None and 0 <= _pull_gidx < MAX_TRACKS and self._track_bufs is not None) else mix[:frames, :2]
                        if tmp_view is not None:
                            try:
                                if src is tmp_view:
                                    src[:, 0] *= float(gl)
                                    src[:, 1] *= float(gr)
                                    _pull_dest += src
                                else:
                                    np.multiply(src, (float(gl), float(gr)), out=tmp_view, casting='unsafe')
                                    _pull_dest += tmp_view
                            except Exception:
                                pass
                        else:
                            try:
                                src[:, 0] *= float(gl)
                                src[:, 1] *= float(gr)
                            except Exception:
                                pass
                            _pull_dest += src
                        continue

                # Fallback (no track routing metadata)
                mix[:frames, :2] += b2
            except Exception:
                pass

        # 9. Master Audio-FX (post-track mix, pre-master volume/pan)
        try:
            master_tid = str(getattr(self, "_master_track_id", "") or "")
            if master_tid and self._track_audio_fx_map:
                master_fx = self._track_audio_fx_map.get(master_tid)
                if master_fx is not None:
                    master_fx.process_inplace(mix, frames, self._sr)
        except Exception:
            pass

        # 10. Master Volume & Pan (smoothed — no clicks!)
        vol = self._master_vol_smooth
        if vol != 1.0:
            mix *= vol

        pan = self._master_pan_smooth
        if abs(pan) > 0.005:
            gl, gr = _pan_gains(1.0, pan)
            mix[:, 0] *= gl
            mix[:, 1] *= gr

        # 9. Soft limiter (numpy C-speed)
        np.clip(mix, -1.0, 1.0, out=mix)

        # 10. Copy to output
        outdata[:frames, :2] = mix[:frames]
        if outdata.shape[1] > 2:
            outdata[:frames, 2:] = 0

        # 11. Write metering ring (lock-free)
        meter = self._meter_ring
        if meter is not None:
            try:
                meter.write(mix[:frames])
            except Exception:
                pass

        # v0.0.20.41: Write master peak directly
        dp = self._direct_peaks_ref
        if dp is not None:
            try:
                mk_l = float(np.max(np.abs(mix[:frames, 0])))
                mk_r = float(np.max(np.abs(mix[:frames, 1])))
                old_m = dp.get("__master__", (0.0, 0.0))
                dp["__master__"] = (max(old_m[0], mk_l), max(old_m[1], mk_r))
            except Exception:
                pass

        # 12. Transport playhead sync (end of block)
        if transport is not None and st is not None:
            try:
                transport._set_external_playhead_samples(
                    int(st.playhead), float(self._sr))
            except Exception:
                pass

    

    def _mix_source_to_track(self, audio: Any, tid: str, frames: int,
                              mix: Any, ts: Any, tmp: Any) -> None:
        """Route a stereo buffer through one track's FX/vol/pan/meter pipeline and add to mix.

        v0.0.20.653: Extracted from pull-source loop for reuse by multi-output routing.
        ZERO-ALLOC: uses pre-allocated tmp buffer.
        """
        try:
            idx = self._track_index_map.get(tid)
            if idx is None:
                # No track index → mix directly (fallback)
                mix[:frames, :2] += audio[:frames, :2]
                return

            vol, pan, audible = ts.get_track_gain(int(idx))
            if not audible:
                return
            gl, gr = _pan_gains(vol, pan)

            # Audio-FX chain (pre-fader, pre-meter)
            src = audio[:frames, :2]
            tmp_view = tmp[:frames, :2] if tmp is not None else None
            fx = None
            try:
                if self._track_audio_fx_map:
                    fx = self._track_audio_fx_map.get(tid)
            except Exception:
                fx = None
            if fx is not None:
                try:
                    if tmp_view is not None:
                        np.copyto(tmp_view, src, casting='unsafe')
                        src = tmp_view
                    fx.process_inplace(src, frames, self._sr)
                except Exception:
                    pass

            # Track metering + direct peaks
            try:
                meter = self.get_track_meter(int(idx))
                meter.update_from_block(src, float(gl), float(gr))
            except Exception:
                pass
            dp = self._direct_peaks_ref
            if dp is not None:
                try:
                    pk_l = float(np.max(np.abs(src[:, 0]))) * abs(gl)
                    pk_r = float(np.max(np.abs(src[:, 1]))) * abs(gr)
                    old = dp.get(tid, (0.0, 0.0))
                    dp[tid] = (max(old[0], pk_l), max(old[1], pk_r))
                except Exception:
                    pass

            # Apply vol/pan then mix into master
            if tmp_view is not None and src is tmp_view:
                src[:, 0] *= float(gl)
                src[:, 1] *= float(gr)
                mix[:frames, :2] += src
            else:
                try:
                    if tmp_view is not None:
                        np.multiply(src, (float(gl), float(gr)), out=tmp_view, casting='unsafe')
                        mix[:frames, :2] += tmp_view
                    else:
                        src[:, 0] *= float(gl)
                        src[:, 1] *= float(gr)
                        mix[:frames, :2] += src
                except Exception:
                    pass
        except Exception:
            pass

    def render_for_jack(self, frames: int, in_bufs, out_bufs, sr: int) -> bool:
        """JACK render callback variant.

        IMPORTANT (v0.0.20.39):
        - Uses the SAME per-track mix pipeline as the sounddevice callback:
          TrackParamState (vol/pan/mute/solo) is applied in real-time.
        - Updates TrackMeterRing for each active track + master meter ring.
        - No stop/play required for mixer changes while looping.
        """
        try:
            self._sr = int(sr)
            if np is None or self._mix_buf is None:
                return False

            frames = int(frames)
            if frames <= 0:
                return False

            # Smoothing coefficient (adapt to current block size)
            tau = 5.0 * float(sr) / 1000.0
            coeff = 1.0 - math.exp(-float(frames) / max(1.0, tau))

            # 1. Drain params (master + per-track) from ring buffer
            ring = self._param_ring
            ts = self._track_state
            if ring is not None:
                try:
                    for pid, val in ring.drain_into(ts):
                        if pid == PARAM_MASTER_VOL:
                            self._master_vol = val
                        elif pid == PARAM_MASTER_PAN:
                            self._master_pan = val
                except Exception:
                    pass

            # 2. Smooth master + track parameters (single-pole IIR)
            self._master_vol_smooth += coeff * (self._master_vol - self._master_vol_smooth)
            self._master_pan_smooth += coeff * (self._master_pan - self._master_pan_smooth)
            ts.advance_smoothing(coeff)

            # 3. Advance RT params if present (backward compat)
            rt = self._rt_params
            if rt is not None:
                try:
                    rt.advance(frames, self._sr)
                except Exception:
                    pass

            # 4. Zero the mix buffer slice
            mix = self._mix_buf[:frames]
            mix.fill(0.0)

            # 5. Transport playhead sync (start of block)
            st = self._arrangement_state
            transport = self._transport_ref
            if transport is not None:
                try:
                    ph = int(st.playhead) if st is not None else int(self._silence_playhead)
                    transport._set_external_playhead_samples(ph, float(self._sr))
                except Exception:
                    pass

            # 6. Arrangement render (per-track mix: TrackParamState + TrackMeterRing)
            if st is not None:
                try:
                    if (np is not None and hasattr(st, "get_active_tracks")
                            and hasattr(st, "render_track") and hasattr(st, "advance")
                            and self._track_bufs is not None):
                        tracks = st.get_active_tracks(frames, out=self._active_tracks_buf)
                        ts2 = self._track_state

                        for track_idx in tracks:
                            if track_idx < 0 or track_idx >= MAX_TRACKS:
                                continue

                            vol, pan, audible = ts2.get_track_gain(int(track_idx))
                            if not audible:
                                continue

                            tb = self._track_bufs[int(track_idx)]
                            st.render_track(int(track_idx), frames, out=tb)

                            # Audio-FX chain (pre-fader, pre-meter)
                            try:
                                tid = self._track_index_to_id.get(int(track_idx))
                                if tid is not None and self._track_audio_fx_map:
                                    fx = self._track_audio_fx_map.get(str(tid))
                                    if fx is not None:
                                        fx.process_inplace(tb, frames, self._sr)
                            except Exception:
                                pass

                            gl, gr = _pan_gains(vol, pan)

                            # VU metering (peak + decay), lock-free
                            meter_t = self.get_track_meter(int(track_idx))
                            meter_t.update_from_block(tb[:frames], gl, gr)

                            # v0.0.20.41: Direct peaks for JACK too
                            dp = self._direct_peaks_ref
                            if dp is not None:
                                try:
                                    tid = self._track_index_to_id.get(int(track_idx))
                                    if tid is not None:
                                        pk_l = float(np.max(np.abs(tb[:frames, 0]))) * abs(gl)
                                        pk_r = float(np.max(np.abs(tb[:frames, 1]))) * abs(gr)
                                        old = dp.get(tid, (0.0, 0.0))
                                        dp[tid] = (max(old[0], pk_l), max(old[1], pk_r))
                                except Exception:
                                    pass

                            # Apply vol/pan in-place then mix into master
                            tb[:frames, 0] *= float(gl)
                            tb[:frames, 1] *= float(gr)
                            mix[:frames] += tb[:frames]

                        # Advance playhead ONCE for the whole block
                        st.advance(frames)
                    else:
                        # Fallback: legacy full-mix render
                        buf = st.render(frames)
                        if buf is not None:
                            mix[:buf.shape[0]] += buf[:frames]
                except Exception:
                    pass
            else:
                try:
                    if transport is not None and bool(getattr(transport, "playing", False)):
                        self._silence_playhead += frames
                except Exception:
                    pass

            # 7. Process real-time MIDI events → Sampler (v0.0.20.42)
            if st is not None and self._sampler_registry is not None:
                bypassed_j = self._bypassed_track_ids
                try:
                    midi_evts = st.get_pending_midi_events(frames)
                    for evt in midi_evts:
                        try:
                            # v0.0.20.80: Skip MIDI for bypassed instruments
                            if str(evt.track_id) in bypassed_j:
                                continue
                            if evt.is_note_on:
                                self._sampler_registry.note_on(
                                    str(evt.track_id), int(evt.pitch), int(evt.velocity),
                                    pitch_offset_semitones=float(getattr(evt, "pitch_offset_semitones", 0.0) or 0.0),
                                    micropitch_curve=list(getattr(evt, "micropitch_curve", None) or []),
                                    note_duration_samples=int(getattr(evt, "note_duration_samples", 0) or 0))
                            else:
                                self._sampler_registry.note_off(str(evt.track_id), pitch=int(evt.pitch))
                        except Exception:
                            pass
                except Exception:
                    pass

            # 8. Pull sources (Sampler/Drum/SF2/etc.) WITH per-track gain/pan + metering
            #    v0.0.20.653: Multi-output plugin routing support.
            #    When a pull source has _pydaw_output_count > 1 and returns (frames, 2*N),
            #    outputs are split and routed to child tracks via _plugin_output_map.
            ts_pull = self._track_state
            bypassed_jp = self._bypassed_track_ids
            tmp = self._block_buf[:frames] if self._block_buf is not None else None
            po_map = self._plugin_output_map  # parent_tid -> {out_idx: child_tid}
            for fn in self._pull_sources:
                try:
                    # v0.0.20.80: Check instrument bypass before pulling audio
                    tid_attr = getattr(fn, "_pydaw_track_id", None)
                    tid = tid_attr() if callable(tid_attr) else tid_attr
                    tid = str(tid) if tid not in (None, "", "None") else ""
                    if tid and tid in bypassed_jp:
                        continue

                    b = fn(frames, self._sr)
                    if b is None:
                        continue

                    # v0.0.20.653: Multi-output routing
                    output_count = int(getattr(fn, "_pydaw_output_count", 1) or 1)
                    output_routes = po_map.get(tid) if (tid and po_map and output_count > 1) else None

                    if output_routes and b.shape[1] >= output_count * 2:
                        # Multi-output: split buffer and route each output pair
                        # Output 0 → parent track (always)
                        out0 = b[:frames, 0:2]
                        if tid:
                            self._mix_source_to_track(out0, tid, frames, mix, ts_pull, tmp)
                        else:
                            mix[:frames, :2] += out0

                        # Outputs 1+ → child tracks
                        for out_idx, child_tid in output_routes.items():
                            try:
                                out_idx = int(out_idx)
                                if out_idx < 1 or out_idx >= output_count:
                                    continue
                                ch_start = out_idx * 2
                                ch_end = ch_start + 2
                                if ch_end > b.shape[1]:
                                    continue
                                out_buf = b[:frames, ch_start:ch_end]
                                if child_tid and child_tid not in bypassed_jp:
                                    self._mix_source_to_track(out_buf, child_tid, frames, mix, ts_pull, tmp)
                            except Exception:
                                continue
                    else:
                        # Single-output (standard path — backwards compatible)
                        b2 = b[:frames, :2]

                        if tid:
                            self._mix_source_to_track(b2, tid, frames, mix, ts_pull, tmp)
                        else:
                            mix[:frames, :2] += b2
                except Exception:
                    pass

            # 9. Master Audio-FX (post-track mix, pre-master volume/pan)
            try:
                master_tid = str(getattr(self, "_master_track_id", "") or "")
                if master_tid and self._track_audio_fx_map:
                    master_fx = self._track_audio_fx_map.get(master_tid)
                    if master_fx is not None:
                        master_fx.process_inplace(mix, frames, self._sr)
            except Exception:
                pass

            # 10. Master Volume & Pan (smoothed — no clicks!)
            vol = self._master_vol_smooth
            if vol != 1.0:
                mix *= vol

            pan = self._master_pan_smooth
            if abs(pan) > 0.005:
                gl, gr = _pan_gains(1.0, pan)
                mix[:, 0] *= gl
                mix[:, 1] *= gr

            # 9. Soft limiter (numpy C-speed)
            np.clip(mix, -1.0, 1.0, out=mix)

            # 10. JACK output (de-interleaved)
            if out_bufs:
                try:
                    if len(out_bufs) >= 1:
                        out_bufs[0][:frames] = mix[:frames, 0]
                    if len(out_bufs) >= 2:
                        out_bufs[1][:frames] = mix[:frames, 1]
                except Exception:
                    return False

            # 11. Write master metering ring (lock-free)
            meter = self._meter_ring
            if meter is not None:
                try:
                    meter.write(mix[:frames])
                except Exception:
                    pass

            # v0.0.20.41: Direct master peak for JACK
            dp = self._direct_peaks_ref
            if dp is not None:
                try:
                    mk_l = float(np.max(np.abs(mix[:frames, 0])))
                    mk_r = float(np.max(np.abs(mix[:frames, 1])))
                    old_m = dp.get("__master__", (0.0, 0.0))
                    dp["__master__"] = (max(old_m[0], mk_l), max(old_m[1], mk_r))
                except Exception:
                    pass

            # 12. Transport playhead sync (end of block)
            if transport is not None and st is not None:
                try:
                    transport._set_external_playhead_samples(int(st.playhead), float(self._sr))
                except Exception:
                    pass

            return True
        except Exception:
            return False

class HybridEngineBridge:
    """Bridge between GUI thread and HybridAudioCallback.

    All methods on this class are GUI-thread safe.

    v0.0.20.14: Per-track parameter control + track index registry.
    """

    def __init__(self, rt_params: Optional[RTParamStore] = None):
        self._param_ring = ParamRingBuffer(capacity=512)
        self._meter_ring = AudioRingBuffer(capacity=16384, channels=2)

        self._callback = HybridAudioCallback(
            param_ring=self._param_ring,
            meter_ring=self._meter_ring,
            rt_params=rt_params,
        )

        self._track_meters: Dict[str, TrackMeterRing] = {}
        # Track ID → index mapping (GUI thread writes, audio thread reads atomically)
        self._track_id_to_idx: Dict[str, int] = {}
        self._next_track_idx: int = 0

    @property
    def callback(self) -> HybridAudioCallback:
        return self._callback

    @property
    def param_ring(self) -> ParamRingBuffer:
        return self._param_ring

    @property
    def meter_ring(self) -> AudioRingBuffer:
        return self._meter_ring

    # ---- Track index registry (GUI thread)

    def register_track(self, track_id: str) -> int:
        """Register a track and get its ring buffer index."""
        if track_id in self._track_id_to_idx:
            return self._track_id_to_idx[track_id]
        idx = self._next_track_idx
        self._next_track_idx += 1
        self._track_id_to_idx[track_id] = idx
        # Update callback's mapping (atomic swap)
        self._callback.set_track_index_map(dict(self._track_id_to_idx))
        return idx

    def get_track_idx(self, track_id: str) -> int:
        """Get track index, registering if needed."""
        return self.register_track(track_id)

    def set_track_index_map(self, mapping: Dict[str, int]) -> None:
        """Set deterministic Track-ID→Index mapping (project order).

        v0.0.20.25: Keeps ArrangementState track_idx aligned with GUI + audio thread.
        """
        try:
            clean: Dict[str, int] = {}
            for k, v in dict(mapping or {}).items():
                try:
                    idx = int(v)
                except Exception:
                    continue
                if idx < 0 or idx >= MAX_TRACKS:
                    continue
                clean[str(k)] = idx

            self._track_id_to_idx = clean
            self._next_track_idx = (max(clean.values()) + 1) if clean else 0
            self._callback.set_track_index_map(dict(self._track_id_to_idx))
        except Exception:
            pass

    # ---- Audio-FX chain (main thread → audio thread)

    def set_track_audio_fx_map(self, fx_map: Dict[str, Any]) -> None:
        """Provide compiled per-track Audio-FX chains to the audio thread.

        Called from GUI thread when project snapshot changes.
        """
        try:
            self._callback.set_track_audio_fx_map(fx_map)
        except Exception:
            pass

    def set_master_track_id(self, track_id: str) -> None:
        try:
            self._callback.set_master_track_id(track_id)
        except Exception:
            pass

    # ---- Master parameter updates (GUI thread, lock-free via ring)

    def set_master_volume(self, vol: float) -> None:
        self._param_ring.push(PARAM_MASTER_VOL, max(0.0, min(1.0, float(vol))))

    def set_master_pan(self, pan: float) -> None:
        self._param_ring.push(PARAM_MASTER_PAN, max(-1.0, min(1.0, float(pan))))

    # ---- Per-track parameter updates (GUI thread, lock-free via ring)

    def set_track_volume(self, track_id: str, vol: float) -> None:
        """Set track volume from GUI thread (0.0-1.0)."""
        idx = self.get_track_idx(track_id)
        self._param_ring.push_track_param(idx, TRACK_VOL,
                                          max(0.0, min(1.0, float(vol))))

    def set_track_pan(self, track_id: str, pan: float) -> None:
        """Set track pan from GUI thread (-1.0 to 1.0)."""
        idx = self.get_track_idx(track_id)
        self._param_ring.push_track_param(idx, TRACK_PAN,
                                          max(-1.0, min(1.0, float(pan))))

    def set_track_mute(self, track_id: str, muted: bool) -> None:
        """Set track mute from GUI thread."""
        idx = self.get_track_idx(track_id)
        self._param_ring.push_track_param(idx, TRACK_MUTE,
                                          1.0 if muted else 0.0)

    def set_track_solo(self, track_id: str, solo: bool) -> None:
        """Set track solo from GUI thread."""
        idx = self.get_track_idx(track_id)
        self._param_ring.push_track_param(idx, TRACK_SOLO,
                                          1.0 if solo else 0.0)

    # ---- Arrangement state (atomic reference swap)

    def set_arrangement_state(self, state: Any) -> None:
        self._callback.set_arrangement_state(state)

    def set_pull_sources(self, sources: List[Any]) -> None:
        self._callback.set_pull_sources(sources)

    def set_bypassed_track_ids(self, bypassed: set) -> None:
        """Update instrument bypass set (GUI thread). Atomic swap."""
        self._callback.set_bypassed_track_ids(bypassed)

    def set_plugin_output_map(self, output_map: Dict[str, Dict[int, str]]) -> None:
        """Update multi-output plugin routing (GUI thread). Atomic swap.

        v0.0.20.653: Routes plugin output pairs to child tracks.
        output_map: parent_track_id -> {output_idx: child_track_id}
        """
        self._callback.set_plugin_output_map(output_map)

    def set_transport_ref(self, transport: Any) -> None:
        self._callback.set_transport_ref(transport)

    def set_sample_rate(self, sr: int) -> None:
        self._callback._sr = int(sr)

    # ---- Metering (GUI reads lock-free from audio ring)

    def read_master_peak(self) -> Tuple[float, float]:
        return self._meter_ring.read_peak(frames=512)

    # ---- Track meter helpers (GUI thread)

    def try_get_track_idx(self, track_id: str) -> Optional[int]:
        """Return track index if known, without registering.

        IMPORTANT: This must not allocate / mutate. Safe to call from audio thread
        if needed, but we primarily use it for RT-safe metering hooks.
        """
        try:
            return self._track_id_to_idx.get(str(track_id))
        except Exception:
            return None

    def get_track_meter(self, track_id: str) -> TrackMeterRing:
        """Get the live TrackMeterRing for track_id (backed by HybridAudioCallback)."""
        idx = self.get_track_idx(track_id)  # GUI thread OK: may register
        return self._callback.get_track_meter(int(idx))

    def read_track_peak(self, track_id: str) -> Tuple[float, float]:
        """Read per-track peak levels (GUI thread, lock-free).

        Note: The authoritative meters live in HybridAudioCallback.
        """
        try:
            idx = self._track_id_to_idx.get(str(track_id))
            if idx is None:
                # GUI thread: register on demand (keeps backward compat)
                idx = self.get_track_idx(track_id)
            meter = self._callback.get_track_meter(int(idx))
            return meter.read_and_decay()
        except Exception:
            return (0.0, 0.0)

    # ---- JACK integration (v0.0.20.14)

    def jack_render_callback(self, frames: int, in_bufs, out_bufs,
                             sr: int) -> bool:
        """Direct JACK process callback using HybridAudioCallback.

        Drop-in replacement for DSPJackEngine.render_callback.
        Uses zero-lock ring buffer pipeline instead of RTParamStore.
        """
        return self._callback.render_for_jack(frames, in_bufs, out_bufs, sr)


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------

_global_bridge: Optional[HybridEngineBridge] = None


def get_hybrid_bridge(rt_params: Optional[RTParamStore] = None) -> HybridEngineBridge:
    """Get or create the global hybrid engine bridge."""
    global _global_bridge
    if _global_bridge is None:
        _global_bridge = HybridEngineBridge(rt_params=rt_params)
    return _global_bridge
