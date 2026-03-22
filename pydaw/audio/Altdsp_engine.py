"""
Realtime DSP + JACK bridge engine (minimal-invasive).

Goals:
- Keep existing GUI + project logic intact.
- Provide a single place to SUM multiple audio sources and apply MASTER gain/pan.
- Run as JACK render callback through JackClientService so PyDAW appears in qpwgraph.
- Be ultra-defensive: never raise from realtime callback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any

import numpy as np

try:
    # shared pan helper used elsewhere in the project
    from .arrangement_renderer import _pan_gains
except Exception:  # pragma: no cover
    def _pan_gains(gain: float, pan: float) -> tuple[float, float]:
        # equal-power-ish simple pan fallback
        pan = float(max(-1.0, min(1.0, pan)))
        # map [-1..1] -> [0..1]
        x = (pan + 1.0) * 0.5
        import math
        l = math.cos(x * math.pi * 0.5) * gain
        r = math.sin(x * math.pi * 0.5) * gain
        return float(l), float(r)


MasterGetter = Callable[[], tuple[float, float]]  # (volume, pan)
PullSource = Callable[[int, int], Optional[np.ndarray]]  # (frames, sr) -> stereo float32 (frames,2)


@dataclass
class _MixState:
    arrangement_state: Any = None
    pull_sources: Dict[str, PullSource] = None
    master_getter: Optional[MasterGetter] = None
    transport_ref: Any = None


class DSPJackEngine:
    """DSP mixing engine used as JACK render callback."""

    def __init__(self) -> None:
        self._state = _MixState(arrangement_state=None, pull_sources={}, master_getter=None, transport_ref=None)
        self._mix_buf: Optional[np.ndarray] = None
        self._mix_buf_frames: int = 0

    # ----- configuration (non-realtime)

    def set_arrangement_state(self, st: Any) -> None:
        self._state.arrangement_state = st

    def set_transport_ref(self, transport: Any) -> None:
        self._state.transport_ref = transport

    def set_master_getter(self, getter: Optional[MasterGetter]) -> None:
        self._state.master_getter = getter

    def register_pull_source(self, name: str, fn: PullSource) -> None:
        if not name:
            return
        if self._state.pull_sources is None:
            self._state.pull_sources = {}
        self._state.pull_sources[str(name)] = fn

    def unregister_pull_source(self, name: str) -> None:
        try:
            if self._state.pull_sources and name in self._state.pull_sources:
                self._state.pull_sources.pop(name, None)
        except Exception:
            pass

    # ----- realtime

    def render_callback(self, frames: int, in_bufs, out_bufs, sr: int) -> bool:  # noqa: ANN001
        try:
            frames_i = int(frames)
            if frames_i <= 0 or frames_i > 8192:
                return False
            sr_i = int(sr) if int(sr) > 0 else 48000

            # Ensure mix buffer
            if self._mix_buf is None or self._mix_buf_frames < frames_i:
                alloc = max(frames_i, 2048)
                self._mix_buf = np.zeros((alloc, 2), dtype=np.float32)
                self._mix_buf_frames = alloc

            mix = self._mix_buf[:frames_i]
            mix[:] = 0.0

            st = self._state.arrangement_state

            # 1) Arrangement render
            if st is not None:
                try:
                    buf = st.render(frames_i)
                    if isinstance(buf, np.ndarray) and buf.ndim == 2 and buf.shape[0] >= frames_i and buf.shape[1] >= 2:
                        mix[:, 0] += buf[:frames_i, 0].astype(np.float32, copy=False)
                        mix[:, 1] += buf[:frames_i, 1].astype(np.float32, copy=False)
                        # external playhead update (no Qt signals)
                        try:
                            tr = self._state.transport_ref
                            if tr is not None and hasattr(tr, "_set_external_playhead_samples"):
                                tr._set_external_playhead_samples(int(getattr(st, "playhead", 0)), float(sr_i))
                        except Exception:
                            pass
                except Exception:
                    pass

            # 2) Additional pull sources
            try:
                ps = self._state.pull_sources or {}
                for _name, fn in list(ps.items()):
                    if not callable(fn):
                        continue
                    try:
                        b = fn(frames_i, sr_i)
                        if isinstance(b, np.ndarray) and b.ndim == 2 and b.shape[0] >= frames_i and b.shape[1] >= 2:
                            mix[:, 0] += b[:frames_i, 0].astype(np.float32, copy=False)
                            mix[:, 1] += b[:frames_i, 1].astype(np.float32, copy=False)
                    except Exception:
                        continue
            except Exception:
                pass

            # 3) Master volume/pan (LIVE)
            try:
                vol = 1.0
                pan = 0.0
                mg = self._state.master_getter
                if mg is not None:
                    v, p = mg()
                    vol = float(v)
                    pan = float(p)
                vol = 0.0 if vol < 0.0 else (1.0 if vol > 1.0 else vol)
                pan = -1.0 if pan < -1.0 else (1.0 if pan > 1.0 else pan)

                if abs(vol - 1.0) > 1e-6:
                    mix *= vol
                if abs(pan) > 0.01:
                    gl, gr = _pan_gains(1.0, pan)
                    mix[:, 0] *= np.float32(gl)
                    mix[:, 1] *= np.float32(gr)
            except Exception:
                pass

            # 4) Clamp and write to outputs
            try:
                np.clip(mix, -1.0, 1.0, out=mix)
            except Exception:
                pass

            try:
                if out_bufs and len(out_bufs) >= 1:
                    out_bufs[0][:frames_i] = mix[:, 0]
                if out_bufs and len(out_bufs) >= 2:
                    out_bufs[1][:frames_i] = mix[:, 1]
                if out_bufs and len(out_bufs) > 2:
                    for ch in range(2, len(out_bufs)):
                        try:
                            out_bufs[ch][:frames_i] = 0.0
                        except Exception:
                            pass
            except Exception:
                return False

            return True
        except Exception:
            return False
