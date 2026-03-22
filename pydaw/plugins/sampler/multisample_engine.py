# -*- coding: utf-8 -*-
"""Multi-Sample Engine — polyphonic sampler with zone-based mapping.

v0.0.20.656 — AP7 Phase 7A

Architecture:
- Each active voice is a lightweight VoiceState that references a SampleZone
- Voices use per-sample DSP from the existing dsp.py module
- The engine loads sample data once per zone and caches it
- Round-robin is handled by MultiSampleMap
- Modulation matrix is evaluated per-voice per-block

This does NOT modify the existing ProSamplerEngine. It is a NEW engine
that coexists with the existing one.
"""

from __future__ import annotations

import math
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .dsp import (
    clamp, lerp, softclip, limiter_soft,
    BiquadDF2T, rbj_biquad, rbj_lowshelf, rbj_highshelf,
)
from .audio_io import load_audio
from .multisample_model import (
    SampleZone, MultiSampleMap, ZoneEnvelope, ZoneFilter,
    ZoneLFO, ModulationSlot,
)

log = logging.getLogger(__name__)

# Maximum polyphony
MAX_VOICES = 32


@dataclass
class EnvState:
    """ADSR envelope state machine."""
    stage: str = "idle"   # idle, attack, hold, decay, sustain, release
    level: float = 0.0
    counter: int = 0

    def reset(self) -> None:
        self.stage = "idle"
        self.level = 0.0
        self.counter = 0

    def trigger(self) -> None:
        self.stage = "attack"
        self.level = 0.0
        self.counter = 0

    def release_env(self) -> None:
        if self.stage not in ("idle", "release"):
            self.stage = "release"
            self.counter = 0

    def step(self, env: ZoneEnvelope, sr: float) -> float:
        """Advance one sample and return envelope level."""
        if self.stage == "idle":
            return 0.0

        if self.stage == "attack":
            a_samples = max(1, int(env.attack * sr))
            self.level += 1.0 / a_samples
            self.counter += 1
            if self.level >= 1.0:
                self.level = 1.0
                self.stage = "hold"
                self.counter = 0
            return self.level

        if self.stage == "hold":
            h_samples = max(0, int(env.hold * sr))
            self.counter += 1
            if self.counter >= h_samples:
                self.stage = "decay"
                self.counter = 0
            return 1.0

        if self.stage == "decay":
            d_samples = max(1, int(env.decay * sr))
            self.counter += 1
            t = min(1.0, self.counter / d_samples)
            self.level = 1.0 + (env.sustain - 1.0) * t
            if t >= 1.0:
                self.stage = "sustain"
                self.counter = 0
                self.level = env.sustain
            return self.level

        if self.stage == "sustain":
            self.level = env.sustain
            return self.level

        if self.stage == "release":
            r_samples = max(1, int(env.release * sr))
            self.counter += 1
            t = min(1.0, self.counter / r_samples)
            release_start = self.level if self.counter == 1 else self.level
            self.level = self.level * (1.0 - 1.0 / r_samples)
            if t >= 1.0 or self.level < 0.0001:
                self.level = 0.0
                self.stage = "idle"
            return self.level

        return 0.0


@dataclass
class LFOState:
    """LFO oscillator state."""
    phase: float = 0.0

    def step(self, lfo: ZoneLFO, sr: float) -> float:
        """Advance one sample and return LFO value (-1..1)."""
        inc = (2.0 * math.pi * lfo.rate_hz) / sr
        self.phase += inc
        if self.phase > 2.0 * math.pi:
            self.phase -= 2.0 * math.pi

        shape = lfo.shape
        p = self.phase

        if shape == "sine":
            return math.sin(p)
        elif shape == "triangle":
            v = (2.0 / math.pi) * p
            if p < math.pi:
                return v - 1.0
            else:
                return 3.0 - v
        elif shape == "square":
            return 1.0 if p < math.pi else -1.0
        elif shape == "saw":
            return (p / math.pi) - 1.0
        else:  # random / S&H — simplified
            return math.sin(p * 7.13) * math.cos(p * 3.91)

    def reset(self) -> None:
        self.phase = 0.0


@dataclass
class VoiceState:
    """State for one active voice."""
    zone_id: str = ""
    note: int = 60
    velocity: int = 100
    position: float = 0.0        # sample position (fractional)
    pitch_ratio: float = 1.0     # playback speed ratio

    amp_env: EnvState = field(default_factory=EnvState)
    filter_env: EnvState = field(default_factory=EnvState)
    lfo1: LFOState = field(default_factory=LFOState)
    lfo2: LFOState = field(default_factory=LFOState)

    filt: Optional[BiquadDF2T] = field(default=None, repr=False)

    active: bool = False
    releasing: bool = False

    def init_filter(self) -> None:
        if self.filt is None:
            self.filt = BiquadDF2T()


class MultiSampleEngine:
    """Polyphonic multi-sample engine.

    Usage:
        engine = MultiSampleEngine(target_sr=48000)
        engine.set_map(multi_sample_map)
        engine.note_on(60, 100)
        audio = engine.pull(1024, 48000)  # -> (1024, 2) float32
        engine.note_off(60)
    """

    def __init__(self, target_sr: int = 48000) -> None:
        self.target_sr = int(target_sr)
        self._lock = threading.RLock()
        self._map = MultiSampleMap()
        self._voices: List[VoiceState] = [VoiceState() for _ in range(MAX_VOICES)]

        # Sample cache: zone_id -> mono float32 numpy array
        self._sample_cache: Dict[str, np.ndarray] = {}

        # Master output
        self.master_gain: float = 0.8
        self.master_pan: float = 0.0

    def set_map(self, sample_map: MultiSampleMap) -> None:
        """Set/replace the multi-sample map."""
        with self._lock:
            self._map = sample_map
            self._preload_samples()

    def get_map(self) -> MultiSampleMap:
        """Get the current map (thread-safe copy reference)."""
        return self._map

    def _preload_samples(self) -> None:
        """Load all zone samples into cache."""
        for zone in self._map.zones:
            self._load_zone_sample(zone)

    def _load_zone_sample(self, zone: SampleZone) -> bool:
        """Load a single zone's sample into cache. Returns True on success."""
        if zone.zone_id in self._sample_cache:
            return True
        path = zone.sample_path
        if not path or not Path(path).exists():
            return False
        try:
            data, sr = load_audio(path, target_sr=self.target_sr)
            # Store as mono for processing
            mono = data.mean(axis=1).astype(np.float32, copy=False)
            self._sample_cache[zone.zone_id] = mono
            return True
        except Exception as e:
            log.warning("Failed to load sample for zone %s: %s", zone.zone_id, e)
            return False

    def load_zone_sample(self, zone: SampleZone) -> bool:
        """Public API to load a zone's sample (thread-safe)."""
        with self._lock:
            return self._load_zone_sample(zone)

    def unload_zone_sample(self, zone_id: str) -> None:
        """Remove a zone's sample from cache."""
        with self._lock:
            self._sample_cache.pop(zone_id, None)

    # ---- Note events ----

    def note_on(self, note: int, velocity: int = 100) -> None:
        """Trigger note-on: find matching zones and allocate voices."""
        with self._lock:
            zones = self._map.find_zones(int(note), int(velocity))
            for zone in zones:
                if zone.zone_id not in self._sample_cache:
                    continue
                voice = self._alloc_voice()
                if voice is None:
                    break  # no free voices
                self._activate_voice(voice, zone, int(note), int(velocity))

    def note_off(self, note: int) -> None:
        """Release all voices playing the given note."""
        with self._lock:
            for v in self._voices:
                if v.active and not v.releasing and v.note == int(note):
                    v.releasing = True
                    v.amp_env.release_env()
                    v.filter_env.release_env()

    def all_notes_off(self) -> None:
        """Release all active voices."""
        with self._lock:
            for v in self._voices:
                if v.active:
                    v.releasing = True
                    v.amp_env.release_env()
                    v.filter_env.release_env()

    def panic(self) -> None:
        """Immediately silence all voices."""
        with self._lock:
            for v in self._voices:
                v.active = False
                v.amp_env.reset()
                v.filter_env.reset()

    def _alloc_voice(self) -> Optional[VoiceState]:
        """Find a free voice slot. Steals oldest releasing voice if all busy."""
        # First: find inactive voice
        for v in self._voices:
            if not v.active:
                return v
        # Second: steal oldest releasing voice
        for v in self._voices:
            if v.releasing:
                return v
        # Third: steal first voice (voice stealing)
        return self._voices[0] if self._voices else None

    def _activate_voice(self, voice: VoiceState, zone: SampleZone,
                        note: int, velocity: int) -> None:
        """Configure and start a voice for the given zone."""
        voice.zone_id = zone.zone_id
        voice.note = note
        voice.velocity = velocity
        voice.active = True
        voice.releasing = False

        # Calculate pitch ratio
        tune_total = zone.tune_semitones + zone.tune_cents / 100.0
        voice.pitch_ratio = 2.0 ** ((note - zone.root_note + tune_total) / 12.0)

        # Sample start position
        samples = self._sample_cache.get(zone.zone_id)
        if samples is not None:
            n = len(samples)
            voice.position = float(int(zone.sample_start * n))
        else:
            voice.position = 0.0

        # Init envelopes
        voice.amp_env = EnvState()
        voice.amp_env.trigger()
        voice.filter_env = EnvState()
        voice.filter_env.trigger()

        # Init LFOs
        voice.lfo1 = LFOState()
        voice.lfo2 = LFOState()

        # Init filter
        voice.init_filter()
        if voice.filt is not None:
            voice.filt.reset()

    # ---- Audio rendering ----

    def pull(self, frames: int, sr: int) -> Optional[np.ndarray]:
        """Pull audio buffer. Returns (frames, 2) float32 or None if silent."""
        with self._lock:
            # Check for any active voices
            any_active = any(v.active for v in self._voices)
            if not any_active:
                return None

            out = np.zeros((frames, 2), dtype=np.float32)
            sr_f = float(sr)

            for voice in self._voices:
                if not voice.active:
                    continue

                zone = self._map.get_zone(voice.zone_id)
                if zone is None:
                    voice.active = False
                    continue

                samples = self._sample_cache.get(voice.zone_id)
                if samples is None:
                    voice.active = False
                    continue

                n_samples = len(samples)
                if n_samples < 2:
                    voice.active = False
                    continue

                self._render_voice(out, voice, zone, samples, n_samples,
                                   frames, sr_f)

            # Master gain + pan
            mg = float(self.master_gain)
            mp = float(self.master_pan)
            ang = (mp + 1.0) * 0.25 * math.pi
            gl = mg * math.cos(ang) * 1.4142
            gr = mg * math.sin(ang) * 1.4142
            out[:, 0] *= gl
            out[:, 1] *= gr

            # Soft limit
            np.clip(out, -1.0, 1.0, out=out)

            return out

    def _render_voice(self, out: np.ndarray, voice: VoiceState,
                      zone: SampleZone, samples: np.ndarray,
                      n_samples: int, frames: int, sr: float) -> None:
        """Render one voice into the output buffer."""
        vel01 = float(voice.velocity) / 127.0
        zone_gain = float(zone.gain)
        zone_pan = float(zone.pan)

        # Sample boundaries
        s_start = int(zone.sample_start * n_samples)
        s_end = int(zone.sample_end * n_samples)
        if s_end <= s_start + 1:
            s_end = min(n_samples, s_start + 2)

        loop_enabled = zone.loop.enabled
        loop_start = int(zone.loop.start_norm * n_samples) if loop_enabled else s_start
        loop_end = int(zone.loop.end_norm * n_samples) if loop_enabled else s_end
        if loop_end <= loop_start + 1:
            loop_end = min(n_samples, loop_start + 2)

        # Pan
        ang = (zone_pan + 1.0) * 0.25 * math.pi
        pan_l = math.cos(ang) * 1.4142
        pan_r = math.sin(ang) * 1.4142

        # Filter setup
        use_filter = zone.filter.filter_type != "off"
        filt = voice.filt

        pos = voice.position
        pitch = voice.pitch_ratio

        for i in range(frames):
            # Envelopes
            amp_e = voice.amp_env.step(zone.amp_envelope, sr)
            filt_e = voice.filter_env.step(zone.filter_envelope, sr)

            if amp_e < 0.00001:
                if voice.amp_env.stage == "idle":
                    voice.active = False
                    break
                continue

            # Modulation
            lfo1_val = voice.lfo1.step(zone.lfo1, sr)
            lfo2_val = voice.lfo2.step(zone.lfo2, sr)

            # Apply modulation matrix
            mod_pitch = 0.0
            mod_cutoff = 0.0
            mod_amp = 0.0
            mod_pan = 0.0

            for slot in zone.mod_slots:
                if slot.source == "none" or slot.destination == "none":
                    continue
                if abs(slot.amount) < 0.001:
                    continue

                # Get source value (-1..1)
                src_val = 0.0
                if slot.source == "lfo1":
                    src_val = lfo1_val
                elif slot.source == "lfo2":
                    src_val = lfo2_val
                elif slot.source == "env_amp":
                    src_val = amp_e * 2.0 - 1.0  # 0..1 -> -1..1
                elif slot.source == "env_filter":
                    src_val = filt_e * 2.0 - 1.0
                elif slot.source == "velocity":
                    src_val = vel01 * 2.0 - 1.0
                elif slot.source == "key_track":
                    src_val = (float(voice.note) - 60.0) / 60.0

                # Apply to destination
                mod_val = src_val * slot.amount
                if slot.destination == "pitch":
                    mod_pitch += mod_val
                elif slot.destination == "filter_cutoff":
                    mod_cutoff += mod_val
                elif slot.destination == "amp":
                    mod_amp += mod_val
                elif slot.destination == "pan":
                    mod_pan += mod_val

            # Effective pitch (with modulation)
            eff_pitch = pitch
            if abs(mod_pitch) > 0.001:
                eff_pitch *= 2.0 ** (mod_pitch * 2.0 / 12.0)  # ±2 semitones per unit

            # Read sample (linear interpolation)
            idx = int(pos)
            frac = pos - idx

            if idx >= s_end - 1:
                if loop_enabled:
                    pos = float(loop_start) + (pos - float(loop_end))
                    idx = int(pos)
                    frac = pos - idx
                    if idx < 0 or idx >= n_samples - 1:
                        pos = float(loop_start)
                        idx = int(pos)
                        frac = 0.0
                else:
                    voice.active = False
                    voice.amp_env.reset()
                    break

            if 0 <= idx < n_samples - 1:
                x = float(samples[idx]) * (1.0 - frac) + float(samples[idx + 1]) * frac
            elif idx < n_samples:
                x = float(samples[idx])
            else:
                x = 0.0

            # Filter with envelope modulation
            if use_filter and filt is not None:
                base_cutoff = float(zone.filter.cutoff_hz)
                mod_c = base_cutoff * (1.0 + filt_e * zone.filter.env_amount + mod_cutoff * 4000.0)
                mod_c = max(20.0, min(20000.0, mod_c))
                ft = zone.filter.filter_type
                q = float(zone.filter.resonance)
                try:
                    coeffs = rbj_biquad(ft if ft in ("lp", "hp", "bp") else "lp",
                                        mod_c, sr, q)
                    filt.set_coeffs(*coeffs)
                except Exception:
                    pass
                x = float(filt.process(x))

            # Apply amplitude
            gain = zone_gain * vel01 * amp_e * (1.0 + mod_amp * 0.5)
            gain = max(0.0, min(2.0, gain))

            # Effective pan
            eff_pan = zone_pan + mod_pan * 0.5
            eff_pan = max(-1.0, min(1.0, eff_pan))
            p_ang = (eff_pan + 1.0) * 0.25 * math.pi
            pl = math.cos(p_ang) * 1.4142
            pr = math.sin(p_ang) * 1.4142

            out[i, 0] += x * gain * pl
            out[i, 1] += x * gain * pr

            pos += eff_pitch

        voice.position = pos

    # ---- State management ----

    def export_state(self) -> Dict[str, Any]:
        """Export full state for project save."""
        with self._lock:
            return {
                "sample_map": self._map.to_dict(),
                "master_gain": self.master_gain,
                "master_pan": self.master_pan,
            }

    def import_state(self, d: Dict[str, Any]) -> None:
        """Import state from project load."""
        with self._lock:
            sm = d.get("sample_map")
            if isinstance(sm, dict):
                self._map = MultiSampleMap.from_dict(sm)
            self.master_gain = float(d.get("master_gain", 0.8))
            self.master_pan = float(d.get("master_pan", 0.0))
            self._preload_samples()

    def active_voice_count(self) -> int:
        """Return number of currently active voices."""
        return sum(1 for v in self._voices if v.active)


__all__ = ["MultiSampleEngine", "MAX_VOICES"]
