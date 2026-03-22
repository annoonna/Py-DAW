"""Optimized Realtime DSP + JACK bridge engine (v0.0.20.1).

Zero-Glitch-Policy:
- No locks in render_callback
- No memory allocations in render_callback
- No Python exceptions propagated from render_callback
- Pre-allocated mix buffer (8192 × 2 float32)
- Pre-cached pull sources list (no dict iteration)
- RTParamStore smoothing (5ms exponential) for click-free parameter changes
"""
from __future__ import annotations

import math
import numpy as np
from typing import Callable, Optional, Dict, Any

_HALF_PI = 1.5707963267948966  # π/2 pre-calculated


def _pan_gains_fast(gain: float, pan: float) -> tuple[float, float]:
    """Equal-power pan law. Returns (left_gain, right_gain)."""
    pan = float(max(-1.0, min(1.0, pan)))
    x = (pan + 1.0) * 0.5
    return (math.cos(x * _HALF_PI) * gain,
            math.sin(x * _HALF_PI) * gain)


MasterGetter = Callable[[], tuple[float, float]]
PullSource = Callable[[int, int], Optional[np.ndarray]]


class DSPJackEngine:
    """Realtime DSP engine for JACK and sounddevice backends.

    Integrates with RTParamStore for smoothed parameter reads.
    """

    def __init__(self, rt_params=None) -> None:
        # State
        self.arrangement_state = None
        self.transport_ref = None
        self.master_getter = None  # legacy fallback

        # RT parameter store (optional — falls back to master_getter)
        self.rt_params = rt_params

        # Pre-cached pull sources (no dict overhead in callback)
        self._pull_sources_dict: Dict[str, PullSource] = {}
        self._pull_sources_list: list[PullSource] = []

        # Pre-allocated buffers (prevents allocation in callback)
        self._mix_buf = np.zeros((8192, 2), dtype=np.float32)
        self._tmp_buf = np.zeros((8192, 2), dtype=np.float32)

        # Optional: HybridEngineBridge for metering/track mapping in Live/Preview mode
        self._hybrid_bridge = None

        # Performance flags
        self._has_transport_playhead = False

        # Realtime playhead fallback
        self._rt_playhead_samples = 0
        self._rt_restart_requested = False

    # ---- Configuration (non-realtime, may be slow)

    def set_arrangement_state(self, st: Any) -> None:
        self.arrangement_state = st

    def set_transport_ref(self, transport: Any) -> None:
        self.transport_ref = transport
        self._has_transport_playhead = hasattr(
            transport, "_set_external_playhead_samples"
        )

    def set_hybrid_bridge(self, bridge: Any) -> None:
        """Bind HybridEngineBridge to push metering in Live/Preview mode."""
        self._hybrid_bridge = bridge

    def set_master_getter(self, getter: Optional[MasterGetter]) -> None:
        """Legacy master vol/pan getter. Used when rt_params is None."""
        self.master_getter = getter

    def register_pull_source(self, name: str, fn: PullSource) -> None:
        self._pull_sources_dict[name] = fn
        self._update_cache()

    def unregister_pull_source(self, name: str) -> None:
        self._pull_sources_dict.pop(name, None)
        self._update_cache()

    def _update_cache(self) -> None:
        self._pull_sources_list = list(self._pull_sources_dict.values())

    def request_restart_playhead(self) -> None:
        """Request playhead restart at next render callback."""
        self._rt_restart_requested = True

    # ---- REALTIME CALLBACK (must be extremely fast)

    def render_callback(self, frames: int, in_bufs, out_bufs,
                        sr: int) -> bool:
        try:
            # 0. Advance RT param smoothing for this block
            rt = self.rt_params
            if rt is not None:
                rt.advance(frames, sr)

            # 1. Sample-accurate restart
            if self._rt_restart_requested:
                self._rt_restart_requested = False
                st = self.arrangement_state
                if st is not None:
                    try:
                        if bool(getattr(st, 'loop_enabled', False)):
                            st.playhead = int(getattr(st, 'loop_start', 0))
                        else:
                            st.playhead = 0
                    except Exception:
                        st.playhead = 0
                self._rt_playhead_samples = 0

            # 2. Zero the mix buffer (no allocation!)
            mix = self._mix_buf[:frames]
            mix.fill(0.0)

            # 3. Provide START playhead to Transport
            st = self.arrangement_state
            if self._has_transport_playhead and self.transport_ref is not None:
                try:
                    ph = int(st.playhead) if st is not None else int(
                        self._rt_playhead_samples)
                    self.transport_ref._set_external_playhead_samples(
                        ph, float(sr))
                except Exception:
                    pass

            # 4. Arrangement Render
            if st is not None:
                buf = st.render(frames)
                if buf is not None:
                    mix += buf
            else:
                self._rt_playhead_samples += int(frames)

            # 5. Pull sources (Sampler, SF2, Synths)
            # If pull-source has track-id metadata, apply per-track gain/pan/mute/solo here.
            rt = self.rt_params
            any_solo = False
            try:
                if rt is not None:
                    any_solo = bool(rt.any_solo())
            except Exception:
                any_solo = False

            hb = getattr(self, "_hybrid_bridge", None)
            hcb = getattr(hb, "callback", None) if hb is not None else None
            tmp = self._tmp_buf[:frames]

            for fn in self._pull_sources_list:
                try:
                    b = fn(frames, sr)
                    if b is None:
                        continue

                    b2 = b[:frames, :2]

                    tid_attr = getattr(fn, "_pydaw_track_id", None)
                    tid = tid_attr() if callable(tid_attr) else tid_attr
                    tid = str(tid) if tid not in (None, "", "None") else ""

                    if tid and rt is not None:
                        # Mute/Solo
                        try:
                            if rt.is_track_muted(tid):
                                continue
                        except Exception:
                            pass
                        try:
                            if any_solo and (not rt.is_track_solo(tid)):
                                continue
                        except Exception:
                            pass

                        try:
                            tv = float(rt.get_track_vol(tid))
                        except Exception:
                            tv = 1.0
                        try:
                            tp = float(rt.get_track_pan(tid))
                        except Exception:
                            tp = 0.0

                        gl, gr = _pan_gains_fast(tv, tp)

                        # Track metering
                        try:
                            if hb is not None and hcb is not None:
                                idx = None
                                try_get = getattr(hb, "try_get_track_idx", None)
                                if callable(try_get):
                                    idx = try_get(tid)
                                if idx is None:
                                    idx = hb.get_track_idx(tid)
                                if idx is not None:
                                    meter = hcb.get_track_meter(int(idx))
                                    meter.update_from_block(b2, float(gl), float(gr))
                        except Exception:
                            pass

                        # Apply gains without allocations
                        np.multiply(b2, (float(gl), float(gr)), out=tmp, casting="unsafe")
                        mix += tmp
                    else:
                        mix += b2
                except Exception:
                    pass

            # 6. Master Volume & Pan (smoothed via RTParamStore)
            if rt is not None:
                vol = rt.get_smooth("master:vol", 0.8)
                pan = rt.get_smooth("master:pan", 0.0)
            else:
                # Legacy fallback
                mg = self.master_getter
                if mg is not None:
                    vol, pan = mg()
                else:
                    vol, pan = 1.0, 0.0

            if vol != 1.0:
                mix *= vol

            if abs(pan) > 0.005:
                gl, gr = _pan_gains_fast(1.0, pan)
                mix[:, 0] *= gl
                mix[:, 1] *= gr

            # 7. Soft limiter
            np.clip(mix, -1.0, 1.0, out=mix)

            # 7b. Metering: push master block into hybrid meter ring (so Mixer VU moves)
            try:
                hb = getattr(self, "_hybrid_bridge", None)
                if hb is not None:
                    hb.meter_ring.write(mix[:frames, :2])
            except Exception:
                pass

            # 8. Output to soundcard (JACK)
            if out_bufs:
                out_bufs[0][:frames] = mix[:, 0]
                out_bufs[1][:frames] = mix[:, 1]

            # 9. Provide END playhead to Transport
            if self._has_transport_playhead and self.transport_ref is not None:
                try:
                    ph = int(st.playhead) if st is not None else int(
                        self._rt_playhead_samples)
                    self.transport_ref._set_external_playhead_samples(
                        ph, float(sr))
                except Exception:
                    pass

            return True
        except Exception:
            # Emergency: deliver silence
            return False
