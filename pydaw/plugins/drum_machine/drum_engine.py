# -*- coding: utf-8 -*-
"""Drum Machine audio engine (pull-based).

Design constraints:
- DO NOT change DAW core: engine must look like existing sampler engines.
- Per-slot isolation: each pad owns its own ProSamplerEngine instance.
- Pull API: pull(frames, sr) -> (frames,2) float32 or None.
- Note trigger API: trigger_note(pitch, velocity, duration_ms) -> bool.

This makes it compatible with the existing SamplerRegistry routing:
MainWindow routes note_preview to the selected track's registered engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Any

import numpy as np

from pydaw.plugins.sampler.sampler_engine import ProSamplerEngine

# Optional: per-slot Audio-FX chain (reuses track Audio-FX DSP, UI-only integration)
try:
    from pydaw.audio.fx_chain import ChainFx
except Exception:  # pragma: no cover
    ChainFx = None  # type: ignore


AUDIO_EXTS = {".wav", ".flac", ".ogg", ".mp3", ".aif", ".aiff"}


@dataclass
class DrumSlotState:
    index: int
    name: str
    sample_path: str = ""
    # Semitone offset for per-pad tuning (UI knob). Applied at trigger time.
    tune_semitones: int = 0
    # v0.0.20.656: Choke group (0 = no choke, 1-8 = mutual exclusion groups)
    # When a pad triggers, all other pads in the same choke group are silenced.
    # Classic use: Hi-Hat Open (group 1) + Hi-Hat Closed (group 1)
    choke_group: int = 0
    # Additional per-slot UI state can go here later (pattern roles, colors, etc.)
    # Per-slot Audio-FX chain (unlimited devices). JSON-safe, persisted in instrument_state.
    audio_fx_chain: dict = field(default_factory=lambda: {
        "type": "chain",
        "enabled": True,
        "mix": 1.0,
        "wet_gain": 1.0,
        "devices": [],
    })


class DrumSlot:
    """One pad/slot: isolated sampler engine + metadata."""

    def __init__(self, index: int, name: str, base_note: int = 36, target_sr: int = 48000):
        self.state = DrumSlotState(index=int(index), name=str(name), sample_path="")
        self.engine = ProSamplerEngine(target_sr=int(target_sr))
        self.base_note = int(base_note)
        self.set_midi_note(self.base_note + int(index))

        # Per-slot Audio-FX chain (compiled ChainFx)
        self._slot_fx_id: str = ""
        self._slot_fx: Any = None

        # Make it a bit lighter by default (drums usually want no huge FX)
        try:
            self.engine.set_filter(ftype="off")
            self.engine.set_fx(chorus_mix=0.0, delay_mix=0.0, reverb_mix=0.0)
            self.engine.set_distortion(0.0)
            self.engine.set_textures(0.0)
            self.engine.set_grain(0.0)
        except Exception:
            pass

    def set_midi_note(self, note: int) -> None:
        note = int(max(0, min(127, note)))
        try:
            self.engine.set_root(note)
        except Exception:
            try:
                self.engine.root_note = note
            except Exception:
                pass

    def has_sample(self) -> bool:
        return bool(self.engine.samples is not None)

    def load_sample(self, path: str) -> bool:
        p = Path(str(path))
        if p.suffix.lower() not in AUDIO_EXTS:
            return False
        ok = bool(self.engine.load_wav(str(p)))
        if ok:
            self.state.sample_path = str(p)
        return ok

    def clear_sample(self) -> None:
        try:
            with self.engine._lock:
                self.engine.samples = None
                self.engine.sample_name = ""
                self.engine.state.playing = False
        except Exception:
            pass
        self.state.sample_path = ""

    # ---------------- Slot Audio-FX Chain
    def fx_id(self, track_id: str = "") -> str:
        """Stable fx-id used as RTParamStore prefix (per track + slot)."""
        tid = str(track_id or "")
        if tid:
            return f"{tid}:slot{int(self.state.index)}"
        # fallback: per-instance stable enough for a session
        if not self._slot_fx_id:
            self._slot_fx_id = f"slotfx:{id(self) & 0xFFFF:04x}:{int(self.state.index)}"
        return self._slot_fx_id

    def rebuild_slot_fx(self, track_id: str, rt_params: Any, *, max_frames: int = 8192) -> None:
        """Rebuild compiled ChainFx for this slot from state.audio_fx_chain.

        Must be called from GUI thread after structural changes (add/remove/enable).
        Param changes only need RTParam updates (no rebuild).
        """
        if ChainFx is None:
            self._slot_fx = None
            return
        try:
            fx_tid = self.fx_id(track_id)
            chain_spec = getattr(self.state, "audio_fx_chain", None)
            self._slot_fx = ChainFx(track_id=fx_tid, chain_spec=chain_spec, rt_params=rt_params, max_frames=int(max_frames))
        except Exception:
            self._slot_fx = None

    def process_slot_fx_inplace(self, buf, frames: int, sr: int) -> None:  # noqa: ANN001
        fx = self._slot_fx
        if fx is None:
            return
        try:
            fx.process_inplace(buf, int(frames), int(sr))
        except Exception:
            return



class DrumMachineEngine:
    """Summing engine for N drum slots.

    v0.0.20.654: Multi-output support.
    When multi_output_enabled=True, pull() returns (frames, 2*output_count) where
    each stereo pair corresponds to one output channel.
    Output 0 = parent track (unmapped pads also land here).
    Output 1..N = individual pad outputs routed via HybridAudioCallback._plugin_output_map.
    """

    def __init__(self, slots: int = 16, base_note: int = 36, target_sr: int = 48000, *, rt_params: Any = None, track_id: str = ""):
        self.base_note = int(base_note)
        self.target_sr = int(target_sr)

        # Slot-FX context (RTParamStore + owning track id)
        self._rt_params: Any = rt_params
        self._track_id: str = str(track_id or "")

        default_names = [
            "Kick", "Snare", "CHat", "OHat",
            "Clap", "Tom", "Perc", "Rim",
            "FX1", "FX2", "Ride", "Crash",
            "Pad13", "Pad14", "Pad15", "Pad16",
        ]
        self.slots: List[DrumSlot] = []
        for i in range(int(slots)):
            nm = default_names[i] if i < len(default_names) else f"Pad{i+1}"
            self.slots.append(DrumSlot(i, nm, base_note=self.base_note, target_sr=self.target_sr))

        # Build per-slot FX chains (safe; no-op if rt_params is None)
        try:
            if self._rt_params is not None:
                self.rebuild_all_slot_fx()
        except Exception:
            pass

        # Cache to reduce allocations on sum
        self._mix_buf: Optional[np.ndarray] = None

        # v0.0.20.654: Multi-output state
        self._multi_output_enabled: bool = False
        self._output_count: int = 1   # 1 = stereo (default), 16 = full multi-output
        self._multi_buf: Optional[np.ndarray] = None  # (frames, 2*output_count)
        # Per-slot output assignment: slot_index -> output_index (0-based)
        # Default: slot i → output i (if multi-output) or all → 0 (if stereo)
        self._slot_output_map: List[int] = list(range(min(slots, 16)))

    # ── v0.0.20.656: Pad Bank expansion ──────────────────────────────────

    def expand_slots(self, total: int) -> None:
        """Expand to `total` slots (safe: only adds, never removes existing).

        Used for pad-bank switching: 4 banks × 16 pads = 64.
        """
        total = int(max(len(self.slots), min(128, total)))
        while len(self.slots) < total:
            i = len(self.slots)
            nm = f"Pad{i+1}"
            self.slots.append(DrumSlot(i, nm, base_note=self.base_note, target_sr=self.target_sr))
            if i < len(self._slot_output_map):
                pass
            else:
                self._slot_output_map.append(0)
        # Rebuild FX for new slots
        try:
            if self._rt_params is not None:
                for s in self.slots[len(self._slot_output_map):]:
                    try:
                        s.rebuild_slot_fx(self._track_id, self._rt_params)
                    except Exception:
                        pass
        except Exception:
            pass

    # ── Multi-output configuration ────────────────────────────────────────

    @property
    def multi_output_enabled(self) -> bool:
        return self._multi_output_enabled

    @property
    def output_count(self) -> int:
        return self._output_count if self._multi_output_enabled else 1

    def set_multi_output(self, enabled: bool, output_count: int = 16) -> None:
        """Enable/disable multi-output mode.

        enabled: True for per-pad outputs, False for stereo sum.
        output_count: number of stereo output pairs (1..16). Typically 16 (one per pad).
        """
        self._multi_output_enabled = bool(enabled)
        self._output_count = max(1, min(len(self.slots), int(output_count)))
        # Invalidate multi-buf cache (will be re-allocated on next pull)
        self._multi_buf = None

    def set_slot_output(self, slot_index: int, output_index: int) -> None:
        """Assign a slot to a specific output pair.

        slot_index: 0..15 (pad index)
        output_index: 0..output_count-1 (0 = parent track, 1+ = child tracks)
        """
        if 0 <= slot_index < len(self._slot_output_map):
            self._slot_output_map[slot_index] = max(0, int(output_index))

    # ── Slot FX management ────────────────────────────────────────────────

    def set_fx_context(self, track_id: str, rt_params: Any) -> None:
        """Set the FX context (track_id + RTParamStore) for per-slot FX chains."""
        self._track_id = str(track_id or "")
        self._rt_params = rt_params
        try:
            self.rebuild_all_slot_fx()
        except Exception:
            pass

    def rebuild_all_slot_fx(self) -> None:
        """Rebuild compiled ChainFx for all slots.

        Safe: no-op if rt_params is None or ChainFx unavailable.
        """
        for s in self.slots:
            try:
                s.rebuild_slot_fx(self._track_id, self._rt_params)
            except Exception:
                pass

    # ---------------- Mapping
    def pitch_to_slot_index(self, pitch: int) -> Optional[int]:
        try:
            p = int(pitch)
        except Exception:
            return None
        idx = p - int(self.base_note)
        if 0 <= idx < len(self.slots):
            return int(idx)
        return None

    # ---------------- Note APIs (compatible with SamplerRegistry)
    def trigger_note(self, pitch: int, velocity: int = 100, duration_ms: int | None = None) -> bool:
        idx = self.pitch_to_slot_index(pitch)
        if idx is None:
            return False
        slot = self.slots[idx]

        # v0.0.20.656: Choke group — silence all other pads in same group
        choke = int(getattr(slot.state, "choke_group", 0) or 0)
        if choke > 0:
            for other in self.slots:
                if other is slot:
                    continue
                if int(getattr(other.state, "choke_group", 0) or 0) == choke:
                    try:
                        other.engine.state.playing = False
                        other.engine._note_off_locked()
                    except Exception:
                        try:
                            other.engine.state.playing = False
                        except Exception:
                            pass

        # Keep per-slot root stable, but allow Tune knob to change the pitch by
        # triggering a different MIDI note (root stays base_note+idx).
        base_pitch = int(self.base_note + idx)
        try:
            semis = int(getattr(slot.state, "tune_semitones", 0) or 0)
        except Exception:
            semis = 0
        trig_pitch = int(max(0, min(127, base_pitch + semis)))
        try:
            slot.engine.set_root(base_pitch)
        except Exception:
            pass
        # v0.0.20.210: Default drums should play until end-of-sample/region.
        return bool(slot.engine.trigger_note(trig_pitch, int(velocity), duration_ms))

    def note_on(self, pitch: int, velocity: int = 100, pitch_offset_semitones: float = 0.0, micropitch_curve: list = None, note_duration_samples: int = 0) -> bool:
        # Drums are usually one-shots; treat note_on as a sustain-less trigger.
        # micropitch_curve is accepted but ignored for drum pads.
        return self.trigger_note(int(round(float(pitch) + float(pitch_offset_semitones or 0.0))), velocity, None)

    def note_off(self) -> None:
        # Not needed for one-shots; keep for API compatibility.
        return

    def all_notes_off(self) -> None:
        for s in self.slots:
            try:
                s.engine.all_notes_off()
            except Exception:
                pass

    def stop_all(self) -> None:
        self.all_notes_off()

    # ---------------- Pull render
    def pull(self, frames: int, sr: int) -> Optional[np.ndarray]:
        """Render audio for all active slots.

        Returns:
        - Multi-output OFF: (frames, 2) stereo sum of all pads
        - Multi-output ON:  (frames, 2*output_count) with per-pad routing

        v0.0.20.654: Multi-output support for per-pad routing to child tracks.
        """
        frames = int(frames)
        if frames <= 0:
            return None
        # v0.0.20.67: Allow sample rate mismatch - better to output than silence.
        if int(sr) != int(self.target_sr):
            if not getattr(self, "_sr_warn_logged", False):
                try:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"DrumMachineEngine: SR mismatch (got {sr}, expected {self.target_sr}). "
                        "Audio may be pitched incorrectly."
                    )
                except Exception:
                    pass
                self._sr_warn_logged = True
            self.target_sr = int(sr)
            for s in self.slots:
                try:
                    s.engine.target_sr = int(sr)
                except Exception:
                    pass

        if self._multi_output_enabled and self._output_count > 1:
            return self._pull_multi_output(frames, sr)
        else:
            return self._pull_stereo(frames, sr)

    def _pull_stereo(self, frames: int, sr: int) -> Optional[np.ndarray]:
        """Original stereo sum path — all pads mixed to one stereo pair."""
        mix = None
        for s in self.slots:
            try:
                b = s.engine.pull(frames, sr)
            except Exception:
                b = None
            if b is None:
                continue
            # Apply per-slot FX chain (post ProSamplerEngine)
            try:
                s.process_slot_fx_inplace(b, frames, sr)
            except Exception:
                pass
            if mix is None:
                # lazily allocate
                if self._mix_buf is None or self._mix_buf.shape[0] != frames:
                    self._mix_buf = np.zeros((frames, 2), dtype=np.float32)
                else:
                    self._mix_buf.fill(0.0)
                mix = self._mix_buf
                mix[:frames, :2] = b[:frames, :2]
            else:
                try:
                    mix[:frames, :2] += b[:frames, :2]
                except Exception:
                    mix[:frames, :2] = mix[:frames, :2] + b[:frames, :2]

        return mix

    def _pull_multi_output(self, frames: int, sr: int) -> Optional[np.ndarray]:
        """Multi-output path — each pad routed to its own stereo pair.

        Returns (frames, 2*output_count) where:
        - Channels 0:2 = Output 0 (parent track — unmapped pads sum here)
        - Channels 2:4 = Output 1 (child track 1)
        - Channels 2N:2N+2 = Output N (child track N)

        v0.0.20.654: Zero-alloc after first call (pre-allocated _multi_buf).
        """
        oc = self._output_count
        total_ch = oc * 2

        # Allocate or reuse multi-output buffer
        if self._multi_buf is None or self._multi_buf.shape != (frames, total_ch):
            self._multi_buf = np.zeros((frames, total_ch), dtype=np.float32)
        else:
            self._multi_buf.fill(0.0)

        has_audio = False
        for i, s in enumerate(self.slots):
            try:
                b = s.engine.pull(frames, sr)
            except Exception:
                b = None
            if b is None:
                continue
            # Apply per-slot FX chain
            try:
                s.process_slot_fx_inplace(b, frames, sr)
            except Exception:
                pass

            # Determine which output this slot goes to
            out_idx = self._slot_output_map[i] if i < len(self._slot_output_map) else 0
            if out_idx < 0 or out_idx >= oc:
                out_idx = 0  # Unmapped → parent track (output 0)

            ch_start = out_idx * 2
            try:
                self._multi_buf[:frames, ch_start:ch_start + 2] += b[:frames, :2]
            except Exception:
                pass
            has_audio = True

        return self._multi_buf if has_audio else None

    # ---------------- Session IO (future)
    def export_state(self) -> dict:
        out = {"base_note": int(self.base_note), "slots": []}
        for s in self.slots:
            try:
                out["slots"].append(
                    {
                        "index": int(s.state.index),
                        "name": str(s.state.name),
                        "sample_path": str(s.state.sample_path),
                        "tune_semitones": int(getattr(s.state, "tune_semitones", 0) or 0),
                        "choke_group": int(getattr(s.state, "choke_group", 0) or 0),
                        "audio_fx_chain": getattr(s.state, "audio_fx_chain", None),
                        "sampler": s.engine.export_state(),
                    }
                )
            except Exception:
                out["slots"].append({"index": int(s.state.index), "name": str(s.state.name), "sample_path": str(s.state.sample_path)})
        return out

    def import_state(self, d: dict) -> None:
        try:
            self.base_note = int(d.get("base_note", self.base_note))
        except Exception:
            pass
        slots = d.get("slots", []) or []
        for sd in slots:
            try:
                idx = int(sd.get("index", -1))
                if not (0 <= idx < len(self.slots)):
                    continue
                s = self.slots[idx]
                s.state.name = str(sd.get("name", s.state.name))
                sp = str(sd.get("sample_path", ""))
                try:
                    s.state.tune_semitones = int(sd.get("tune_semitones", getattr(s.state, "tune_semitones", 0) or 0) or 0)
                except Exception:
                    pass
                # v0.0.20.656: Choke group restore
                try:
                    s.state.choke_group = int(sd.get("choke_group", getattr(s.state, "choke_group", 0) or 0) or 0)
                except Exception:
                    pass
                if sp:
                    s.load_sample(sp)
                # Per-slot FX chain restore
                try:
                    afx = sd.get("audio_fx_chain", None)
                    if isinstance(afx, dict):
                        s.state.audio_fx_chain = afx
                except Exception:
                    pass
                try:
                    sampler_state = sd.get("sampler", None)
                    if sampler_state:
                        s.engine.import_state(sampler_state)
                except Exception:
                    pass
                s.set_midi_note(self.base_note + idx)
            except Exception:
                continue
        # Rebuild compiled slot FX chains after import (safe)
        try:
            if self._rt_params is not None:
                self.rebuild_all_slot_fx()
        except Exception:
            pass

