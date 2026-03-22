"""Fusion Engine — Semi-modular hybrid synthesizer core.

v0.0.20.572: Phase 1 — Voice pool, OSC→FLT→AEG signal path.
v0.0.20.573: Phase 2 — Extended oscillators, filters, envelopes.
v0.0.20.577: Phase 4 — Performance: lock-free pull, vectorized noise/HP,
             local-variable caching in all DSP loops. Fixes GUI freeze
             ("main.py antwortet nicht") and audio stutter.

Interface: compatible with DAW SamplerRegistry (note_on/off/pull).
"""
from __future__ import annotations
import math
import threading
import numpy as np
from typing import Optional

from .voice import Voice
from .oscillators.basic_waves import OSC_REGISTRY, create_oscillator, PulseOscillator
from .filters.svf import FILTER_REGISTRY, create_filter
from .envelopes.adsr import ENV_REGISTRY, create_envelope

# v0.0.20.573: Register Phase 2 modules
try:
    from .oscillators.union import UnionOscillator
    OSC_REGISTRY["union"] = UnionOscillator
except ImportError:
    pass
try:
    from .oscillators.phase1 import Phase1Oscillator
    OSC_REGISTRY["phase-1"] = Phase1Oscillator
except ImportError:
    pass
try:
    from .oscillators.swarm import SwarmOscillator
    OSC_REGISTRY["swarm"] = SwarmOscillator
except ImportError:
    pass
try:
    from .oscillators.bite import BiteOscillator
    OSC_REGISTRY["bite"] = BiteOscillator
except ImportError:
    pass
try:
    from .filters.ladder import LadderFilter, CombFilter
    FILTER_REGISTRY["ladder"] = LadderFilter
    FILTER_REGISTRY["comb"] = CombFilter
except ImportError:
    pass
try:
    from .envelopes.extras import AREnvelope, ADEnvelope, PluckEnvelope
    ENV_REGISTRY["ar"] = AREnvelope
    ENV_REGISTRY["ad"] = ADEnvelope
    ENV_REGISTRY["pluck"] = PluckEnvelope
except ImportError:
    pass
try:
    from .oscillators.wavetable import WavetableOscillator
    OSC_REGISTRY["wavetable"] = WavetableOscillator
except ImportError:
    pass
try:
    from .oscillators.scrawl import ScrawlOscillator
    OSC_REGISTRY["scrawl"] = ScrawlOscillator
except ImportError:
    pass


class FusionEngine:
    """Pull-source synthesizer engine for ChronoScaleStudio.

    Usage:
        engine = FusionEngine(target_sr=48000)
        engine.note_on(60, 100)  # Middle C, velocity 100
        audio = engine.pull(1024, 48000)  # Render 1024 frames
        engine.note_off(60)
    """

    MAX_VOICES = 32
    DEFAULT_VOICES = 8

    def __init__(self, target_sr: int = 48000):
        self._sr = int(target_sr)
        self._lock = threading.Lock()

        # Voice pool
        self._max_poly = self.DEFAULT_VOICES
        self._voices: list[Voice] = [Voice(self._sr) for _ in range(self._max_poly)]

        # Current module types
        self._osc_type = "sine"
        self._flt_type = "svf"
        self._env_type = "adsr"

        # Sub oscillator
        self._sub_osc = PulseOscillator(self._sr)
        self._sub_level = 0.0       # 0..1
        self._sub_octave = -1       # -2, -1, 0
        self._sub_waveform = "pulse"
        self._sub_width = 0.5

        # Noise
        self._noise_level = 0.0     # 0..1
        self._noise_color = 0       # 0=white, 1=pink, 2=brown
        self._pink_state = np.zeros(7, dtype=np.float64)  # for pink noise
        self._brown_state = 0.0

        # Highpass
        self._hp_freq = 20.0
        self._hp_state = 0.0

        # Global controls
        self._glide = 0.0           # seconds
        self._vel_sensitivity = 0.8  # 0..1
        self._gain = 1.0            # linear
        self._pan = 0.0             # -1..+1
        self._output = 1.0          # linear

        # Shared parameter state (synced to all voices)
        self._osc_params: dict[str, float] = {}
        self._flt_params: dict[str, float] = {}
        self._aeg_params: dict[str, float] = {}
        self._feg_params: dict[str, float] = {}
        self._voice_params_dirty = False

        # v0.0.20.576: Scrawl/Wavetable persistent state
        self._scrawl_points: list[tuple[float, float]] = []
        self._scrawl_smooth: bool = True
        self._wt_file_path: str = ""

    # ── MIDI Interface ──

    def note_on(self, pitch: int, velocity: int = 100, **kwargs) -> bool:
        """Trigger a note. Returns True if voice was allocated."""
        with self._lock:
            vel_f = float(velocity) / 127.0
            # Velocity sensitivity scaling
            vel_scaled = 1.0 - self._vel_sensitivity + self._vel_sensitivity * vel_f

            voice = self._allocate_voice(pitch)
            if voice is None:
                return False

            # Apply current module types + params
            voice.swap_oscillator(self._osc_type)
            voice.swap_filter(self._flt_type)
            voice.swap_envelope(self._env_type)

            for k, v in self._osc_params.items():
                voice.osc.set_param(k, v)
            for k, v in self._flt_params.items():
                voice.flt.set_param(k, v)
            for k, v in self._aeg_params.items():
                voice.aeg.set_param(k, v)
            for k, v in self._feg_params.items():
                voice.feg.set_param(k, v)

            # v0.0.20.576: Apply Scrawl/Wavetable state to new voice
            try:
                if self._osc_type == "scrawl" and self._scrawl_points:
                    if hasattr(voice.osc, 'set_points'):
                        voice.osc.set_points(self._scrawl_points)
                        voice.osc.set_param("smooth", 1.0 if self._scrawl_smooth else 0.0)
                elif self._osc_type == "wavetable" and self._wt_file_path:
                    if hasattr(voice.osc, 'load_file'):
                        voice.osc.load_file(self._wt_file_path)
            except Exception:
                pass

            voice.note_on(pitch, velocity)
            return True

    def note_off(self, pitch: int = -1) -> None:
        """Release note(s). pitch=-1 releases all."""
        with self._lock:
            if pitch < 0:
                for v in self._voices:
                    if v.active:
                        v.note_off()
            else:
                for v in self._voices:
                    if v.active and v.pitch == pitch:
                        v.note_off()

    def all_notes_off(self) -> None:
        with self._lock:
            for v in self._voices:
                v.active = False
                v.aeg._stage = 0
                v.feg._stage = 0

    # ── Audio Pull ──

    def pull(self, frames: int, sr: int) -> Optional[np.ndarray]:
        """Render audio. Returns (frames, 2) stereo array or None.

        v0.0.20.577: Lock-free rendering — snapshot active voices under lock,
        then render WITHOUT holding the lock. This prevents GUI freeze when
        knobs are turned during audio callback.
        """
        # --- Snapshot under lock (fast: just list copy) ---
        with self._lock:
            if self._voice_params_dirty:
                self._sync_active_voice_params_locked()
            active = [v for v in self._voices if v.is_active()]
            if not active:
                return None
            # Snapshot parameters that might change from GUI thread
            sub_level = self._sub_level
            sub_octave = self._sub_octave
            noise_level = self._noise_level
            noise_color = self._noise_color
            hp_freq = self._hp_freq
            gain = self._gain
            pan = self._pan
            output = self._output

        # --- Render WITHOUT lock (no GUI contention) ---
        mix = np.zeros(frames, dtype=np.float64)

        # Sub oscillator (shared across voices)
        sub_buf = None
        if sub_level > 0.001:
            sub_freq = active[0].freq * (2.0 ** sub_octave)
            sub_buf = self._sub_osc.render(frames, sub_freq, sr)
            mix += sub_buf * sub_level

        # Render each voice
        for v in active:
            try:
                voice_out = v.render(frames, sr, sub_buf=sub_buf if v.osc._phase_mod > 0 else None)
                mix += voice_out
            except Exception:
                pass

        # Noise generator (vectorized)
        if noise_level > 0.001:
            noise = self._render_noise(frames, noise_color)
            mix += noise * noise_level

        # Highpass filter (vectorized)
        if hp_freq > 25.0:
            mix = self._apply_highpass(mix, sr, hp_freq)

        # Gain (pre-FX)
        mix *= gain

        # Soft clip to prevent harsh digital distortion
        np.tanh(mix, out=mix)

        # Pan → stereo (vectorized, no per-sample loop)
        pan_norm = max(0.0, min(1.0, (pan + 1.0) * 0.5))
        pan_l = math.cos(pan_norm * math.pi * 0.5)
        pan_r = math.sin(pan_norm * math.pi * 0.5)
        stereo = np.empty((frames, 2), dtype=np.float64)
        stereo[:, 0] = mix * (pan_l * output)
        stereo[:, 1] = mix * (pan_r * output)

        return stereo

    # ── Parameter Interface ──

    def _sync_active_voice_params_locked(self) -> None:
        """Apply the latest shared params to active voices.

        v0.0.20.578: MIDI/GUI safety fix — GUI thread only updates shared
        dictionaries under lock. Active voice objects are refreshed here at the
        safe pull-boundary, so audio rendering never sees mid-buffer mutations.
        """
        try:
            active = [v for v in self._voices if v.active]
            if not active:
                self._voice_params_dirty = False
                return
            osc_params = tuple(self._osc_params.items())
            flt_params = tuple(self._flt_params.items())
            aeg_params = tuple(self._aeg_params.items())
            feg_params = tuple(self._feg_params.items())
            for v in active:
                for k, val in osc_params:
                    v.osc.set_param(k, float(val))
                for k, val in flt_params:
                    v.flt.set_param(k, float(val))
                for k, val in aeg_params:
                    v.aeg.set_param(k, float(val))
                for k, val in feg_params:
                    v.feg.set_param(k, float(val))
            self._voice_params_dirty = False
        except Exception:
            self._voice_params_dirty = False

    def set_param(self, key: str, value: float) -> None:
        """Set any engine parameter. Routes to the correct module."""
        with self._lock:
            # Global params
            if key == "polyphony":
                self._set_polyphony(int(round(float(value))))
            elif key == "glide":
                self._glide = max(0.0, min(5.0, float(value)))
            elif key == "vel_sensitivity":
                self._vel_sensitivity = max(0.0, min(1.0, float(value)))
            elif key == "gain":
                self._gain = max(0.0, min(4.0, float(value)))
            elif key == "pan":
                self._pan = max(-1.0, min(1.0, float(value)))
            elif key == "output":
                self._output = max(0.0, min(4.0, float(value)))
            # Sub params
            elif key == "sub_level":
                self._sub_level = max(0.0, min(1.0, float(value)))
            elif key == "sub_octave":
                self._sub_octave = int(round(float(value)))
            elif key == "sub_width":
                self._sub_width = max(0.01, min(0.99, float(value)))
                self._sub_osc.set_param("width", self._sub_width)
            # Noise params
            elif key == "noise_level":
                self._noise_level = max(0.0, min(1.0, float(value)))
            elif key == "noise_color":
                self._noise_color = int(round(float(value))) % 3
            # HP
            elif key == "hp_freq":
                self._hp_freq = max(20.0, min(2000.0, float(value)))
            # Module params (prefix routing)
            elif key.startswith("osc."):
                self._osc_params[key[4:]] = float(value)
                self._voice_params_dirty = True
            elif key.startswith("flt."):
                self._flt_params[key[4:]] = float(value)
                self._voice_params_dirty = True
            elif key.startswith("aeg."):
                self._aeg_params[key[4:]] = float(value)
                self._voice_params_dirty = True
            elif key.startswith("feg."):
                self._feg_params[key[4:]] = float(value)
                self._voice_params_dirty = True

    def get_param(self, key: str) -> float:
        if key == "polyphony":
            return float(self._max_poly)
        if key == "glide":
            return self._glide
        if key == "vel_sensitivity":
            return self._vel_sensitivity
        if key == "gain":
            return self._gain
        if key == "pan":
            return self._pan
        if key == "output":
            return self._output
        if key == "sub_level":
            return self._sub_level
        if key.startswith("osc."):
            return self._osc_params.get(key[4:], 0.0)
        if key.startswith("flt."):
            return self._flt_params.get(key[4:], 0.0)
        if key.startswith("aeg."):
            return self._aeg_params.get(key[4:], 0.0)
        if key.startswith("feg."):
            return self._feg_params.get(key[4:], 0.0)
        return 0.0

    # ── Module Switching ──

    def set_oscillator(self, osc_type: str) -> None:
        """Switch oscillator type for all voices."""
        osc_type = osc_type.lower()
        if osc_type in OSC_REGISTRY:
            with self._lock:
                self._osc_type = osc_type

    def set_filter(self, flt_type: str) -> None:
        flt_type = flt_type.lower()
        if flt_type in FILTER_REGISTRY:
            with self._lock:
                self._flt_type = flt_type

    def set_envelope(self, env_type: str) -> None:
        env_type = env_type.lower()
        if env_type in ENV_REGISTRY:
            with self._lock:
                self._env_type = env_type

    # ── Internal ──

    def _allocate_voice(self, pitch: int) -> Optional[Voice]:
        """Find a free voice or steal the oldest."""
        # First: find an inactive voice
        for v in self._voices:
            if not v.active:
                return v

        # Voice stealing: find the oldest active voice
        oldest = None
        oldest_age = -1
        for v in self._voices:
            if v._age > oldest_age:
                oldest = v
                oldest_age = v._age
        return oldest

    def _set_polyphony(self, n: int) -> None:
        n = max(1, min(self.MAX_VOICES, n))
        if n > len(self._voices):
            for _ in range(n - len(self._voices)):
                self._voices.append(Voice(self._sr))
        self._max_poly = n

    def _render_noise(self, frames: int, color: int = -1) -> np.ndarray:
        """Generate noise of the selected color.

        v0.0.20.577: Vectorized white noise (np.random.randn(frames)).
        Pink/brown still per-sample (stateful) but with local var caching.
        """
        if color < 0:
            color = self._noise_color

        if color == 0:
            # White noise: fully vectorized
            return np.random.randn(frames) * 0.3
        elif color == 1:
            # Pink noise (Voss-McCartney) — stateful, must be per-sample
            # but optimized with local variable caching
            out = np.empty(frames, dtype=np.float64)
            b0, b1, b2, b3, b4, b5, b6 = (
                self._pink_state[0], self._pink_state[1], self._pink_state[2],
                self._pink_state[3], self._pink_state[4], self._pink_state[5],
                self._pink_state[6],
            )
            whites = np.random.randn(frames) * 0.3
            for i in range(frames):
                w = whites[i]
                b0 = 0.99886 * b0 + w * 0.0555179
                b1 = 0.99332 * b1 + w * 0.0750759
                b2 = 0.96900 * b2 + w * 0.1538520
                b3 = 0.86650 * b3 + w * 0.3104856
                b4 = 0.55000 * b4 + w * 0.5329522
                b5 = -0.7616 * b5 - w * 0.0168980
                out[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 1.7874) * 0.11
                b6 = w * 0.115926
            self._pink_state[0] = b0
            self._pink_state[1] = b1
            self._pink_state[2] = b2
            self._pink_state[3] = b3
            self._pink_state[4] = b4
            self._pink_state[5] = b5
            self._pink_state[6] = b6
            return out
        else:
            # Brown noise: local var caching
            out = np.empty(frames, dtype=np.float64)
            state = self._brown_state
            whites = np.random.randn(frames) * 0.02
            for i in range(frames):
                state += whites[i]
                if state > 1.0:
                    state = 1.0
                elif state < -1.0:
                    state = -1.0
                out[i] = state * 0.5
            self._brown_state = state
            return out

    def _apply_highpass(self, buf: np.ndarray, sr: int,
                        hp_freq: float = -1.0) -> np.ndarray:
        """1-pole highpass filter.

        v0.0.20.577: Local variable caching, avoid self lookups in loop.
        """
        if hp_freq < 0:
            hp_freq = self._hp_freq
        rc = 1.0 / (2.0 * math.pi * hp_freq)
        alpha = rc / (rc + 1.0 / sr)
        n = len(buf)
        out = np.empty(n, dtype=np.float64)
        prev_in = 0.0
        state = self._hp_state
        for i in range(n):
            x = buf[i]
            state = alpha * (state + x - prev_in)
            prev_in = x
            out[i] = state
        self._hp_state = state
        return out
