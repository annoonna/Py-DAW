"""
PreviewPlayer: pull-based audio preview source for the Browser.

Design:
- Used as a pull source registered in AudioEngine (sounddevice/JACK).
- Buffer-based playback with optional looping and simple click-safe boundary fades.
- Start-delay in samples for quantized starts (beat/bar aligned).

This module must be realtime-safe in pull(): no heavy allocations or locks.
All heavy work (loading / stretching) happens in background threads,
then set_buffer() swaps the buffer atomically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None


@dataclass
class PreviewState:
    playing: bool = False
    loop: bool = False
    pos: int = 0
    delay: int = 0
    fade_len: int = 128


class PreviewPlayer:
    def __init__(self):
        self._buf = None  # np.ndarray (n,2) float32
        self._sr = 48000
        self._state = PreviewState()

    # ---------------- control

    def set_buffer(self, stereo_f32, sr: int = 48000, loop: bool = False) -> None:
        """Swap buffer (non-RT path)."""
        if np is None:
            return
        try:
            b = np.asarray(stereo_f32, dtype=np.float32)
            if b.ndim == 1:
                b = b.reshape(-1, 1)
            if b.shape[1] == 1:
                b = np.repeat(b, 2, axis=1)
            if b.shape[1] > 2:
                b = b[:, :2]
            self._buf = b
            self._sr = int(sr or 48000)
            # reset position but keep playing state unchanged
            self._state.pos = 0
            self._state.loop = bool(loop)
        except Exception:
            pass

    def start(self, delay_samples: int = 0, loop: Optional[bool] = None) -> None:
        try:
            self._state.delay = max(0, int(delay_samples))
            self._state.pos = 0
            if loop is not None:
                self._state.loop = bool(loop)
            self._state.playing = True
        except Exception:
            pass

    def stop(self) -> None:
        try:
            self._state.playing = False
            self._state.pos = 0
            self._state.delay = 0
        except Exception:
            pass

    def set_loop(self, loop: bool) -> None:
        try:
            self._state.loop = bool(loop)
        except Exception:
            pass

    def is_playing(self) -> bool:
        return bool(getattr(self._state, "playing", False))

    # ---------------- realtime pull

    def pull(self, frames: int, sr: int):
        """Return (frames,2) float32. RT-safe."""
        if np is None:
            return None
        try:
            n = int(frames)
            if n <= 0:
                return None
            out = np.zeros((n, 2), dtype=np.float32)

            buf = self._buf
            st = self._state
            if not st.playing or buf is None or buf.shape[0] <= 1:
                return out

            # If engine sr differs, we still output at engine sr. We assume
            # buffers were pre-rendered at engine sr (48000). Best-effort.
            # (Later: resampler)

            # handle start delay
            if st.delay > 0:
                d = min(n, st.delay)
                st.delay -= d
                if d >= n:
                    return out
                # continue with remaining frames after delay
                start_out = d
                n2 = n - d
            else:
                start_out = 0
                n2 = n

            pos = int(st.pos)
            total = int(buf.shape[0])
            loop = bool(st.loop)

            # helper: apply boundary fades to avoid clicks when wrapping/stopping
            fade_len = int(st.fade_len)
            fade_len = max(0, min(fade_len, 4096))

            def _copy_segment(dst, dst_off, src_off, count, fade_in=False, fade_out=False):
                seg = buf[src_off:src_off+count]
                if seg.shape[0] <= 0:
                    return 0
                if fade_len > 0 and (fade_in or fade_out):
                    k = min(fade_len, seg.shape[0])
                    if k > 0:
                        if fade_in:
                            ramp = (np.arange(k, dtype=np.float32) / float(k)).reshape(-1, 1)
                            seg = seg.copy()
                            seg[:k] *= ramp
                        if fade_out:
                            ramp = (1.0 - (np.arange(k, dtype=np.float32) / float(k))).reshape(-1, 1)
                            if not fade_in:
                                seg = seg.copy()
                            seg[-k:] *= ramp
                dst[dst_off:dst_off+seg.shape[0]] += seg
                return int(seg.shape[0])

            remain = n2
            dst_off = start_out

            while remain > 0 and st.playing:
                if pos >= total:
                    if not loop:
                        # done
                        st.playing = False
                        break
                    pos = 0

                take = min(remain, total - pos)
                # fades:
                fade_in = loop and (pos == 0) and (dst_off > 0 or start_out > 0)
                fade_out = (not loop and (pos + take >= total)) or (loop and (pos + take >= total))
                # When wrapping in same pull, we fade out end and fade in beginning
                wrote = _copy_segment(out, dst_off, pos, take, fade_in=False, fade_out=fade_out)
                dst_off += wrote
                remain -= wrote
                pos += wrote

                if wrote < take:
                    break

                if pos >= total:
                    if loop:
                        # wrap and continue; next iteration will copy from start with fade-in
                        pos = 0
                        # Apply fade-in to the beginning chunk in next copy:
                        if remain > 0:
                            take2 = min(remain, total)
                            wrote2 = _copy_segment(out, dst_off, 0, take2, fade_in=True, fade_out=(loop and take2 >= total))
                            dst_off += wrote2
                            remain -= wrote2
                            pos = wrote2
                    else:
                        st.playing = False
                        break

            st.pos = int(pos)
            return out
        except Exception:
            try:
                return np.zeros((int(frames), 2), dtype=np.float32)
            except Exception:
                return None
