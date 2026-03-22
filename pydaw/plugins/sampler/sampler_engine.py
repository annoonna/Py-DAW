# -*- coding: utf-8 -*-
"""Pro Audio Sampler engine (pull-based, monophonic).

This is the standalone Qt5 sampler engine refactored into a *pull source*:
`pull(frames, sr)` -> (frames,2) float32 or None.

Used for:
- Note preview from PianoRoll/Notation via ProjectService.note_preview
- Manual audition via Play/Loop buttons in the device UI
"""

from __future__ import annotations

import math
import random
import threading
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

import numpy as np

from .dsp import (
    clamp,
    lerp,
    softclip,
    limiter_soft,
    BiquadDF2T,
    DelayLine,
    rbj_biquad,
    rbj_peaking,
    rbj_lowshelf,
    rbj_highshelf,
)
from .audio_io import load_audio


@dataclass
class EngineState:
    playing: bool = False
    position: float = 0.0
    start_position: float = 0.0  # v0.0.20.42: Pro-DAW-Style sample start (0.0=beginning, 1.0=end)
    end_position: float = 1.0    # v0.0.20.210: Pro-DAW-Style sample end   (0.0=beginning, 1.0=end)
    loop_start: float = 0.0
    loop_end: float = 1.0

    gain: float = 0.80
    pan: float = 0.0
    velocity: float = 1.0

    target_pitch: float = 1.0
    current_pitch: float = 1.0
    repitch_ratio: float = 1.0   # v0.0.20.397: User knob multiplier (separate from MIDI note pitch)
    glide_sec: float = 0.02

    lfo_rate_hz: float = 0.8
    lfo_depth: float = 0.0
    lfo_phase: float = 0.0

    noise_mix: float = 0.0
    bitcrush: float = 0.0
    hold_n: int = 1
    hold_count: int = 0
    hold_value: float = 0.0
    quant_levels: int = 0

    filter_type: str = "off"
    cutoff_hz: float = 8000.0
    q: float = 0.707

    drive: float = 1.0
    dist_mix: float = 0.0
    dist_drive: float = 1.0

    chorus_mix: float = 0.0
    delay_mix: float = 0.0
    delay_time_sec: float = 0.35
    delay_fb: float = 0.35
    reverb_mix: float = 0.0

    a: float = 0.01
    h: float = 0.00
    d: float = 0.15
    s: float = 1.00
    r: float = 0.20
    env_stage: str = "idle"
    env_level: float = 0.0
    env_count: int = 0

    # --- Optional EQ (safe default: off)
    eq_enabled: bool = False
    eq1_db: float = 0.0
    eq2_db: float = 0.0
    eq3_db: float = 0.0
    eq4_db: float = 0.0
    eq5_db: float = 0.0


class ProSamplerEngine:
    def __init__(self, target_sr: int = 48000):
        self.target_sr = int(target_sr)
        self.state = EngineState()
        self.samples: Optional[np.ndarray] = None  # mono float32
        self.sample_name: str = ""
        self.root_note: int = 60

        self._filter = BiquadDF2T()
        # Optional EQ5 (insert style, pre-time FX)
        self._eq1 = BiquadDF2T()
        self._eq2 = BiquadDF2T()
        self._eq3 = BiquadDF2T()
        self._eq4 = BiquadDF2T()
        self._eq5 = BiquadDF2T()
        self._chorus = DelayLine(max_samples=int(0.050 * self.target_sr) + 8)
        self._delay = DelayLine(max_samples=int(2.0 * self.target_sr) + 8)
        self._rvb_combs = [
            DelayLine(max_samples=int(0.120 * self.target_sr) + 8),
            DelayLine(max_samples=int(0.150 * self.target_sr) + 8),
            DelayLine(max_samples=int(0.180 * self.target_sr) + 8),
        ]
        self._rvb_comb_delays = [0.097, 0.113, 0.131]
        self._rvb_comb_fb = 0.72
        self._rvb_ap1 = DelayLine(max_samples=int(0.050 * self.target_sr) + 8)
        self._rvb_ap2 = DelayLine(max_samples=int(0.050 * self.target_sr) + 8)
        self._rvb_ap_d1 = 0.011
        self._rvb_ap_d2 = 0.017
        self._rvb_ap_g = 0.65

        self._smooth_gain = self.state.gain
        self._smooth_pan = self.state.pan
        self._smooth_cutoff = self.state.cutoff_hz
        self._smooth_drive = self.state.drive
        self._smooth_mix_ch = self.state.chorus_mix
        self._smooth_mix_dl = self.state.delay_mix
        self._smooth_mix_rv = self.state.reverb_mix
        self._smooth_mix_ds = self.state.dist_mix
        self._chorus_phase = 0.0

        self._lock = threading.RLock()

        # preview lifecycle
        self._preview_remaining: int = 0  # in samples; 0 means not scheduled
        self._loop_enabled: bool = False

        # --- MPE v2: continuous micropitch curve ---
        self._micropitch_curve: list = []  # [(t_norm, semitones), ...]
        self._micropitch_duration: int = 0  # note duration in samples
        self._micropitch_elapsed: int = 0  # frames elapsed since note_on
        self._micropitch_base_pitch: int = 60  # MIDI pitch at note_on

        self._recalc_filter_locked()
        self._recalc_eq_locked()

    # ----- State IO (for future preset/session)
    def export_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": asdict(self.state),
                "root_note": int(self.root_note),
                "loop_enabled": bool(self._loop_enabled),
                "sample_name": str(self.sample_name or ""),  # v0.0.20.75: Include sample path
            }

    def import_state(self, d: Dict[str, Any]) -> None:
        st = d.get("state", {})
        with self._lock:
            for k, v in st.items():
                if hasattr(self.state, k):
                    setattr(self.state, k, v)
            self.root_note = int(d.get("root_note", self.root_note))
            self._loop_enabled = bool(d.get("loop_enabled", self._loop_enabled))
            # Note: sample_name is restored but sample data must be loaded separately
            # via load_wav() since we don't serialize the actual audio data
            self._apply_grain_locked(self.state.bitcrush)
            self._recalc_filter_locked()
            self._recalc_eq_locked()

    # ----- Region (start/end)
    def set_region_norm(self, start: float | None = None, end: float | None = None) -> None:
        """Set playback region in normalized [0..1] units."""
        with self._lock:
            if start is not None:
                self.state.start_position = float(clamp(float(start), 0.0, 1.0))
            if end is not None:
                self.state.end_position = float(clamp(float(end), 0.0, 1.0))
            if float(self.state.end_position) <= float(self.state.start_position) + 0.01:
                self.state.end_position = float(min(1.0, float(self.state.start_position) + 0.01))

    # ----- FX params (extra setters used by DrumMachine)
    def set_delay_params(self, time_sec: float | None = None, fb: float | None = None) -> None:
        with self._lock:
            if time_sec is not None:
                self.state.delay_time_sec = float(clamp(float(time_sec), 0.05, 1.8))
            if fb is not None:
                self.state.delay_fb = float(clamp(float(fb), 0.0, 0.95))

    def set_eq5(self, *, enabled: bool | None = None, b1_db=None, b2_db=None, b3_db=None, b4_db=None, b5_db=None) -> None:  # noqa: ANN001
        with self._lock:
            if enabled is not None:
                self.state.eq_enabled = bool(enabled)
            if b1_db is not None:
                self.state.eq1_db = float(clamp(float(b1_db), -24.0, 24.0))
            if b2_db is not None:
                self.state.eq2_db = float(clamp(float(b2_db), -24.0, 24.0))
            if b3_db is not None:
                self.state.eq3_db = float(clamp(float(b3_db), -24.0, 24.0))
            if b4_db is not None:
                self.state.eq4_db = float(clamp(float(b4_db), -24.0, 24.0))
            if b5_db is not None:
                self.state.eq5_db = float(clamp(float(b5_db), -24.0, 24.0))
            self._recalc_eq_locked()

    # ----- Sample handling
    def load_wav(self, path: str) -> bool:
        try:
            data, sr = load_audio(path, target_sr=self.target_sr)
            # to mono for processing
            mono = data.mean(axis=1).astype(np.float32, copy=False)
            with self._lock:
                self.samples = mono
                self.sample_name = str(path)
                self.state.position = 0.0
                self.state.loop_start = 0.0
                self.state.loop_end = 1.0
                self._rebuild_delaylines_locked()
                self._recalc_filter_locked()
            return True
        except Exception:
            return False

    def set_root(self, note: int) -> None:
        with self._lock:
            self.root_note = int(clamp(int(note), 0, 127))

    def set_loop_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._loop_enabled = bool(enabled)
            if not self._loop_enabled:
                self.state.loop_start = 0.0
                self.state.loop_end = 1.0

    def set_loop_norm(self, ls: float, le: float) -> None:
        with self._lock:
            self.state.loop_start = float(clamp(ls, 0.0, 1.0))
            self.state.loop_end = float(clamp(le, 0.0, 1.0))
            if self.state.loop_end <= self.state.loop_start:
                self.state.loop_end = min(1.0, self.state.loop_start + 0.01)

    # ----- Param setters
    def set_master(self, gain: Optional[float] = None, pan: Optional[float] = None) -> None:
        with self._lock:
            if gain is not None:
                self.state.gain = float(clamp(gain, 0.0, 1.0))
            if pan is not None:
                self.state.pan = float(clamp(pan, -1.0, 1.0))

    def set_velocity(self, vel01: float) -> None:
        with self._lock:
            self.state.velocity = float(clamp(vel01, 0.0, 1.0))

    def set_repitch(self, ratio: float) -> None:
        """v0.0.20.397: Sets user repitch multiplier, separate from MIDI note pitch."""
        with self._lock:
            self.state.repitch_ratio = float(clamp(ratio, 0.25, 4.0))

    def set_glide(self, sec: float) -> None:
        with self._lock:
            self.state.glide_sec = float(clamp(sec, 0.0, 1.0))

    def set_lfo(self, rate_hz: Optional[float] = None, depth: Optional[float] = None) -> None:
        with self._lock:
            if rate_hz is not None:
                self.state.lfo_rate_hz = float(clamp(rate_hz, 0.05, 20.0))
            if depth is not None:
                self.state.lfo_depth = float(clamp(depth, 0.0, 0.20))

    def set_textures(self, noise_mix: float) -> None:
        with self._lock:
            self.state.noise_mix = float(clamp(noise_mix, 0.0, 1.0))

    def set_grain(self, bitcrush_amount: float) -> None:
        with self._lock:
            self.state.bitcrush = float(clamp(bitcrush_amount, 0.0, 1.0))
            self._apply_grain_locked(self.state.bitcrush)

    def _apply_grain_locked(self, amt: float) -> None:
        self.state.hold_n = max(1, 1 + int(amt * 15.0))
        self.state.quant_levels = 0 if amt < 0.15 else max(0, int(8 + amt * 24))

    def set_filter(self, ftype: Optional[str] = None, cutoff_hz: Optional[float] = None, q: Optional[float] = None) -> None:
        with self._lock:
            if ftype is not None:
                self.state.filter_type = str(ftype)
            if cutoff_hz is not None:
                self.state.cutoff_hz = float(clamp(cutoff_hz, 20.0, 20000.0))
            if q is not None:
                self.state.q = float(clamp(q, 0.25, 12.0))
            self._recalc_filter_locked()

    def set_drive(self, drive: float) -> None:
        with self._lock:
            self.state.drive = float(clamp(drive, 1.0, 20.0))

    def set_distortion(self, mix: float) -> None:
        with self._lock:
            self.state.dist_mix = float(clamp(mix, 0.0, 1.0))
            self.state.dist_drive = 1.0 + self.state.dist_mix * 11.0

    def set_fx(self, chorus_mix: Optional[float] = None, delay_mix: Optional[float] = None, reverb_mix: Optional[float] = None) -> None:
        with self._lock:
            if chorus_mix is not None:
                self.state.chorus_mix = float(clamp(chorus_mix, 0.0, 1.0))
            if delay_mix is not None:
                self.state.delay_mix = float(clamp(delay_mix, 0.0, 1.0))
            if reverb_mix is not None:
                self.state.reverb_mix = float(clamp(reverb_mix, 0.0, 1.0))

    def set_env(self, a=None, h=None, d=None, s=None, r=None) -> None:  # noqa: ANN001
        with self._lock:
            if a is not None:
                self.state.a = float(clamp(a, 0.001, 5.0))
            if h is not None:
                self.state.h = float(clamp(h, 0.0, 5.0))
            if d is not None:
                self.state.d = float(clamp(d, 0.001, 5.0))
            if s is not None:
                self.state.s = float(clamp(s, 0.0, 1.0))
            if r is not None:
                self.state.r = float(clamp(r, 0.001, 10.0))

    # ----- Notes / Preview
    
    def load_sample(self, path: str) -> bool:
        """Backwards-compatible alias: `load_sample` -> `load_wav`."""
        return self.load_wav(path)

    def trigger_note(self, pitch: int, velocity: int = 100, duration_ms: Optional[int] = 140, *, pitch_offset_semitones: float = 0.0, micropitch_curve: list = None, note_duration_samples: int = 0) -> bool:
        """Trigger a note (preview-style) if a sample buffer exists.

        - Verifies that a sample buffer is loaded
        - Resets playback pointer to 0
        - Starts ADSR envelope
        - Optionally schedules auto note-off via duration_ms
        """
        pitch = int(pitch)
        velocity = int(velocity)
        ratio = 2.0 ** ((((float(pitch) + float(pitch_offset_semitones or 0.0)) - int(self.root_note)) / 12.0))

        with self._lock:
            # Buffer-check
            if self.samples is None or int(getattr(self.samples, "shape", [0])[0]) < 2:
                return False

            # Voice-activation — start from sample start_position (Pro-DAW-like)
            n_samples = int(getattr(self.samples, "shape", [0])[0])
            sp = float(clamp(float(getattr(self.state, "start_position", 0.0)), 0.0, 1.0))
            ep = float(clamp(float(getattr(self.state, "end_position", 1.0)), 0.0, 1.0))
            if ep <= sp + 0.01:
                ep = float(min(1.0, sp + 0.01))
                self.state.end_position = ep
            start_pos = sp * float(max(1, n_samples))
            end_pos = ep * float(max(1, n_samples))
            start_pos = min(start_pos, max(0.0, end_pos - 1.0))
            self.state.position = float(clamp(start_pos, 0.0, float(max(0, n_samples - 1))))
            self.state.velocity = float(clamp(velocity / 127.0, 0.0, 1.0))
            self.state.target_pitch = float(clamp(ratio, 0.25, 4.0))
            self.state.current_pitch = float(self.state.target_pitch)
            self.state.playing = True

            # --- MPE v2: store continuous micropitch curve ---
            self._micropitch_curve = list(micropitch_curve or [])
            self._micropitch_duration = max(0, int(note_duration_samples or 0))
            self._micropitch_elapsed = 0
            self._micropitch_base_pitch = int(pitch)

            if duration_ms is None:
                self._preview_remaining = 0
            else:
                self._preview_remaining = max(1, int(round((int(duration_ms) / 1000.0) * self.target_sr)))

            self._note_on_locked()
            return True

    def note_on(self, pitch: int, velocity: int = 100, pitch_offset_semitones: float = 0.0, micropitch_curve: list = None, note_duration_samples: int = 0) -> bool:
        """Start a sustained note (until note_off).

        This sampler is currently monophonic. For live-monitoring we simply
        re-use trigger_note() with duration_ms=None (sustain), and stop it via
        note_off().
        """
        try:
            return bool(self.trigger_note(int(pitch), int(velocity), None, pitch_offset_semitones=float(pitch_offset_semitones or 0.0), micropitch_curve=micropitch_curve or [], note_duration_samples=int(note_duration_samples or 0)))
        except Exception:
            return False

    def note_off(self) -> None:
        """Release/stop the currently sustained note."""
        try:
            with self._lock:
                self.state.playing = False
                self._preview_remaining = 0
                self._note_off_locked()
        except Exception:
            pass

    def all_notes_off(self) -> None:
        """Alias for note_off for panic situations."""
        self.note_off()


    def note_on_preview(self, pitch: int, velocity: int = 100, duration_ms: int = 140) -> None:
        """Start a one-shot preview note (auto note-off)."""
        try:
            self.trigger_note(int(pitch), int(velocity), int(duration_ms))
        except Exception:
            pass

    def toggle_play(self) -> bool:
        with self._lock:
            self.state.playing = not self.state.playing
            now = bool(self.state.playing)
            if now:
                # v0.0.20.42: Start from start_position (set by Position slider)
                if self.samples is not None:
                    n = int(self.samples.shape[0])
                    self.state.position = float(self.state.start_position) * float(max(1, n))
                self._preview_remaining = 0
                self._note_on_locked()
            else:
                self._note_off_locked()
            return now

    def stop_play(self) -> None:
        with self._lock:
            self.state.playing = False
            self._preview_remaining = 0
            self._note_off_locked()

    def _note_on_locked(self) -> None:
        self.state.env_stage = "attack"
        self.state.env_level = 0.0
        self.state.env_count = 0

    def _note_off_locked(self) -> None:
        if self.state.env_stage != "idle":
            self.state.env_stage = "release"
            self.state.env_count = 0

    def _env_step_locked(self) -> float:
        sr = max(1, int(self.target_sr))
        def to_samps(sec):  # noqa: ANN001
            return max(1, int(sec * sr))
        st = self.state

        if st.env_stage == "idle":
            return 0.0
        if st.env_stage == "attack":
            n = to_samps(st.a)
            st.env_level += 1.0 / n
            st.env_count += 1
            if st.env_level >= 1.0 or st.env_count >= n:
                st.env_level = 1.0
                st.env_stage = "hold" if st.h > 0 else "decay"
                st.env_count = 0
            return st.env_level
        if st.env_stage == "hold":
            n = to_samps(st.h)
            st.env_count += 1
            if st.env_count >= n:
                st.env_stage = "decay"
                st.env_count = 0
            return st.env_level
        if st.env_stage == "decay":
            n = to_samps(st.d)
            target = st.s
            st.env_level += (target - st.env_level) / n
            st.env_count += 1
            if st.env_count >= n:
                st.env_level = target
                st.env_stage = "sustain"
                st.env_count = 0
            return st.env_level
        if st.env_stage == "sustain":
            st.env_level = st.s
            return st.env_level
        if st.env_stage == "release":
            n = to_samps(st.r)
            st.env_level += (0.0 - st.env_level) / n
            st.env_count += 1
            if st.env_level <= 0.0005 or st.env_count >= n:
                st.env_level = 0.0
                st.env_stage = "idle"
            return st.env_level
        return st.env_level

    def _recalc_filter_locked(self) -> None:
        b0, b1, b2, a1, a2 = rbj_biquad(float(self.target_sr), self.state.filter_type, self.state.cutoff_hz, self.state.q)
        self._filter.set_coeffs(b0, b1, b2, a1, a2)

    def _recalc_eq_locked(self) -> None:
        sr = float(max(1.0, int(self.target_sr)))
        enabled = bool(getattr(self.state, "eq_enabled", False))
        g1 = float(getattr(self.state, "eq1_db", 0.0))
        g2 = float(getattr(self.state, "eq2_db", 0.0))
        g3 = float(getattr(self.state, "eq3_db", 0.0))
        g4 = float(getattr(self.state, "eq4_db", 0.0))
        g5 = float(getattr(self.state, "eq5_db", 0.0))
        if (not enabled) or (abs(g1) + abs(g2) + abs(g3) + abs(g4) + abs(g5) < 1e-6):
            self._eq1.set_coeffs(1.0, 0.0, 0.0, 0.0, 0.0)
            self._eq2.set_coeffs(1.0, 0.0, 0.0, 0.0, 0.0)
            self._eq3.set_coeffs(1.0, 0.0, 0.0, 0.0, 0.0)
            self._eq4.set_coeffs(1.0, 0.0, 0.0, 0.0, 0.0)
            self._eq5.set_coeffs(1.0, 0.0, 0.0, 0.0, 0.0)
            return

        # Fixed, drum-friendly bands
        b0, b1, b2, a1, a2 = rbj_lowshelf(sr, 80.0, 0.9, g1)
        self._eq1.set_coeffs(b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = rbj_peaking(sr, 250.0, 1.0, g2)
        self._eq2.set_coeffs(b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = rbj_peaking(sr, 1000.0, 1.0, g3)
        self._eq3.set_coeffs(b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = rbj_peaking(sr, 4000.0, 1.0, g4)
        self._eq4.set_coeffs(b0, b1, b2, a1, a2)
        b0, b1, b2, a1, a2 = rbj_highshelf(sr, 12000.0, 0.9, g5)
        self._eq5.set_coeffs(b0, b1, b2, a1, a2)

    def _rebuild_delaylines_locked(self) -> None:
        sr = int(self.target_sr)
        self._chorus = DelayLine(max_samples=int(0.050 * sr) + 8)
        self._delay = DelayLine(max_samples=int(2.0 * sr) + 8)
        self._rvb_combs = [
            DelayLine(max_samples=int(0.120 * sr) + 8),
            DelayLine(max_samples=int(0.150 * sr) + 8),
            DelayLine(max_samples=int(0.180 * sr) + 8),
        ]
        self._rvb_ap1 = DelayLine(max_samples=int(0.050 * sr) + 8)
        self._rvb_ap2 = DelayLine(max_samples=int(0.050 * sr) + 8)
        self._filter.reset()
        self._recalc_filter_locked()

    # ----- Pull render
    def pull(self, frames: int, sr: int) -> Optional[np.ndarray]:
        frames = int(frames)
        if frames <= 0:
            return None
        # v0.0.20.67: Allow sample rate mismatch - better to output than silence.
        # If a mismatch exists, the audio may be pitched wrong, but at least there's output.
        # Log a warning once per engine instance.
        if int(sr) != int(self.target_sr):
            if not getattr(self, "_sr_warn_logged", False):
                try:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"ProSamplerEngine: SR mismatch (got {sr}, expected {self.target_sr}). "
                        "Audio may be pitched incorrectly."
                    )
                except Exception:
                    pass
                self._sr_warn_logged = True
            # Update target_sr dynamically to match the audio callback
            with self._lock:
                self.target_sr = int(sr)
                try:
                    self._rebuild_delaylines_locked()
                except Exception:
                    pass
                try:
                    self._recalc_filter_locked()
                    self._recalc_eq_locked()
                except Exception:
                    pass

        with self._lock:
            if self.samples is None:
                return None
            if (not self.state.playing) and (self.state.env_stage == "idle") and (self._preview_remaining <= 0):
                return None

            samples = self.samples
            n = int(samples.shape[0])
            if n <= 1:
                return None

            # loop/region points
            if self._loop_enabled:
                ls = int(self.state.loop_start * n)
                le = int(self.state.loop_end * n)
                if le <= ls:
                    le = n
            else:
                ls = 0
                ep = float(clamp(float(getattr(self.state, "end_position", 1.0)), 0.0, 1.0))
                sp = float(clamp(float(getattr(self.state, "start_position", 0.0)), 0.0, 1.0))
                if ep <= sp + 0.01:
                    ep = float(min(1.0, sp + 0.01))
                    self.state.end_position = ep
                le = int(ep * n)
                le = max(1, min(n, le))

            # smoothing — v0.0.20.398: moderate block-rate smoothing
            # With 1024 frames at 48kHz (~47 blocks/s): sm ≈ 0.15 → ~7 blocks to settle
            # With 8192 frames at 48kHz (~6 blocks/s): sm ≈ 0.70 → ~3 blocks to settle
            sm_block = min(0.70, 0.0001 * frames + 0.05)
            self._smooth_gain = lerp(self._smooth_gain, self.state.gain, sm_block)
            self._smooth_pan = lerp(self._smooth_pan, self.state.pan, sm_block)
            self._smooth_cutoff = lerp(self._smooth_cutoff, self.state.cutoff_hz, sm_block)
            self._smooth_drive = lerp(self._smooth_drive, self.state.drive, sm_block)
            self._smooth_mix_ch = lerp(self._smooth_mix_ch, self.state.chorus_mix, sm_block)
            self._smooth_mix_dl = lerp(self._smooth_mix_dl, self.state.delay_mix, sm_block)
            self._smooth_mix_rv = lerp(self._smooth_mix_rv, self.state.reverb_mix, sm_block)
            self._smooth_mix_ds = lerp(self._smooth_mix_ds, self.state.dist_mix, sm_block)

            # update filter if cutoff moved
            if abs(self._smooth_cutoff - self.state.cutoff_hz) > 5.0:
                self.state.cutoff_hz = float(self._smooth_cutoff)
                self._recalc_filter_locked()

            g = float(self._smooth_gain) * float(self.state.velocity)
            pan = float(self._smooth_pan)
            ang = (pan + 1.0) * 0.25 * math.pi
            gl = g * math.cos(ang) * 1.4142
            gr = g * math.sin(ang) * 1.4142

            glide = float(self.state.glide_sec)
            glide_alpha = 1.0 if glide <= 0.0001 else (1.0 / max(1.0, glide * float(sr)))

            lfo_inc = (2.0 * math.pi * float(self.state.lfo_rate_hz)) / float(sr)
            vib_depth = float(self.state.lfo_depth)

            chorus_rate = 0.15 + float(self.state.lfo_rate_hz) * 0.25
            chorus_inc = (2.0 * math.pi * chorus_rate) / float(sr)
            chorus_mix = float(self._smooth_mix_ch)
            chorus_base = 0.015 * float(sr)
            chorus_depth = (0.002 + 0.006 * chorus_mix) * float(sr)

            delay_mix = float(self._smooth_mix_dl)
            delay_samps = float(clamp(self.state.delay_time_sec, 0.05, 1.8)) * float(sr)
            delay_fb = float(self.state.delay_fb)

            rvb_mix = float(self._smooth_mix_rv)

            noise_mix = float(self.state.noise_mix)
            hold_n = int(self.state.hold_n)
            quant_levels = int(self.state.quant_levels)

            drive = float(self._smooth_drive)
            dist_mix = float(self._smooth_mix_ds)
            dist_drive = float(self.state.dist_drive)

            pos = float(self.state.position)
            preview_remaining = int(self._preview_remaining)

            out = np.zeros((frames, 2), dtype=np.float32)

            for i in range(frames):
                # pitch glide
                self.state.current_pitch += (self.state.target_pitch - self.state.current_pitch) * glide_alpha
                vib = 1.0 + vib_depth * math.sin(self.state.lfo_phase)
                self.state.lfo_phase += lfo_inc
                if self.state.lfo_phase > 2.0 * math.pi:
                    self.state.lfo_phase -= 2.0 * math.pi
                pitch = float(self.state.current_pitch) * vib * float(self.state.repitch_ratio)

                # --- MPE v2: continuous micropitch curve during note ---
                if self._micropitch_curve and self._micropitch_duration > 0:
                    t_norm = float(self._micropitch_elapsed) / float(self._micropitch_duration)
                    if t_norm > 1.0:
                        t_norm = 1.0
                    # inline linear interpolation of curve points
                    curve = self._micropitch_curve
                    mp_semi = 0.0
                    if t_norm <= curve[0][0]:
                        mp_semi = curve[0][1]
                    elif t_norm >= curve[-1][0]:
                        mp_semi = curve[-1][1]
                    else:
                        prev_t, prev_v = curve[0]
                        for ci in range(1, len(curve)):
                            nxt_t, nxt_v = curve[ci]
                            if t_norm <= nxt_t:
                                seg_len = nxt_t - prev_t
                                if seg_len > 1e-9:
                                    a = (t_norm - prev_t) / seg_len
                                    mp_semi = (1.0 - a) * prev_v + a * nxt_v
                                else:
                                    mp_semi = nxt_v
                                break
                            prev_t, prev_v = nxt_t, nxt_v
                    if abs(mp_semi) > 0.001:
                        pitch *= 2.0 ** (mp_semi / 12.0)
                    self._micropitch_elapsed += 1

                env = self._env_step_locked()
                if env <= 0.000001:
                    out[i, 0] = 0.0
                    out[i, 1] = 0.0
                else:
                    idx = int(pos)
                    if idx >= le:
                        if self._loop_enabled:
                            idx = ls
                            pos = float(ls)
                        else:
                            # end of sample, release
                            self.state.playing = False
                            self._note_off_locked()
                            idx = min(n - 1, idx)

                    x = float(samples[idx])

                    # textures/noise
                    if noise_mix > 0.0001:
                        x = x * (1.0 - noise_mix) + ((random.random() * 2.0 - 1.0) * 0.25) * noise_mix

                    # bitcrush (sample hold + optional quantize)
                    if hold_n > 1:
                        self.state.hold_count += 1
                        if self.state.hold_count >= hold_n:
                            self.state.hold_count = 0
                            self.state.hold_value = x
                        x = float(self.state.hold_value)

                    if quant_levels > 0:
                        ql = float(quant_levels)
                        x = round(x * ql) / ql

                    # filter + drive
                    y = float(self._filter.process(x))
                    y *= drive
                    y = softclip(y)

                    # optional EQ5 (insert style)
                    try:
                        if bool(getattr(self.state, "eq_enabled", False)):
                            y = float(self._eq1.process(y))
                            y = float(self._eq2.process(y))
                            y = float(self._eq3.process(y))
                            y = float(self._eq4.process(y))
                            y = float(self._eq5.process(y))
                    except Exception:
                        pass

                    # chorus
                    if chorus_mix > 0.0001:
                        self._chorus_phase += chorus_inc
                        if self._chorus_phase > 2.0 * math.pi:
                            self._chorus_phase -= 2.0 * math.pi
                        d = chorus_base + chorus_depth * (0.5 + 0.5 * math.sin(self._chorus_phase))
                        ch = self._chorus.read_frac(d)
                        self._chorus.write(y)
                        y = y * (1.0 - chorus_mix) + ch * chorus_mix

                    # delay
                    if delay_mix > 0.0001:
                        dl = self._delay.read_frac(delay_samps)
                        self._delay.write(y + dl * delay_fb)
                        y = y * (1.0 - delay_mix) + dl * delay_mix

                    # reverb — v0.0.20.399: send/return with safety clamp
                    if rvb_mix > 0.0001:
                        rv = 0.0
                        for comb, dsec in zip(self._rvb_combs, self._rvb_comb_delays):
                            cd = comb.read_frac(dsec * float(sr))
                            # Clamp feedback input to prevent runaway
                            fb_in = max(-2.0, min(2.0, y + cd * self._rvb_comb_fb))
                            comb.write(fb_in)
                            rv += cd
                        rv *= (1.0 / max(1.0, len(self._rvb_combs)))
                        apd1 = self._rvb_ap1.read_frac(self._rvb_ap_d1 * float(sr))
                        self._rvb_ap1.write(max(-2.0, min(2.0, rv + apd1 * self._rvb_ap_g)))
                        rv = apd1 - rv * self._rvb_ap_g
                        apd2 = self._rvb_ap2.read_frac(self._rvb_ap_d2 * float(sr))
                        self._rvb_ap2.write(max(-2.0, min(2.0, rv + apd2 * self._rvb_ap_g)))
                        rv = apd2 - rv * self._rvb_ap_g
                        # Clamp reverb output
                        rv = max(-1.0, min(1.0, rv))
                        y = y + rv * rvb_mix  # SEND style: dry always passes

                    # distortion
                    if dist_mix > 0.0001:
                        yd = softclip(y * dist_drive)
                        y = y * (1.0 - dist_mix) + yd * dist_mix

                    y *= env
                    out[i, 0] = limiter_soft(y * gl)
                    out[i, 1] = limiter_soft(y * gr)

                    pos += pitch

                # preview countdown
                if preview_remaining > 0:
                    preview_remaining -= 1
                    if preview_remaining == 0:
                        self._preview_remaining = 0
                        self._note_off_locked()

                if (not self.state.playing) and (self.state.env_stage == "idle") and (preview_remaining <= 0) and (not self._loop_enabled):
                    # buffer tail stays zero
                    break

            self.state.position = float(pos)
            self._preview_remaining = int(preview_remaining)

            # finalize
            if self.state.env_stage == "idle" and preview_remaining <= 0 and not self._loop_enabled:
                self.state.playing = False

            return out

# Backward-compatible alias: older code expects SamplerEngine
SamplerEngine = ProSamplerEngine

__all__ = ["ProSamplerEngine", "SamplerEngine"]
