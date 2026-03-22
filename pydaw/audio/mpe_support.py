# -*- coding: utf-8 -*-
"""MPE (MIDI Polyphonic Expression) Support — AP6 Phase 6B, v0.0.20.650.

Implements the MPE specification (MIDI-CA RP-053):
- Per-note pitch bend via per-channel allocation
- Per-note pressure (Channel Pressure / Aftertouch)
- Per-note slide (CC74)
- Zone configuration (Lower/Upper zone)
- Pitch bend range configuration per zone

Architecture:
    ┌─────────────────────────────────────────────┐
    │  MIDI Input (Controller / Keyboard)          │
    │  Roli Seaboard, Linnstrument, Sensel Morph  │
    └──────────────┬──────────────────────────────┘
                   │ Raw MIDI (multi-channel)
                   ▼
    ┌─────────────────────────────────────────────┐
    │  MPEProcessor                                │
    │  - Detects MPE mode from MCM messages        │
    │  - Allocates MIDI channels per note           │
    │  - Routes per-channel PB/AT/CC to per-note    │
    │  - Outputs MidiNote + expressions             │
    └──────────────┬──────────────────────────────┘
                   │ MidiNote with expressions
                   ▼
    ┌─────────────────────────────────────────────┐
    │  Piano Roll / Engine                         │
    │  - Displays per-note pitch bend curve         │
    │  - Displays per-note pressure/slide curves    │
    │  - Engine applies MPE data during playback    │
    └─────────────────────────────────────────────┘

MPE Zones:
    Lower Zone: Manager Channel 1,  Member Channels 2..N
    Upper Zone: Manager Channel 16, Member Channels (16-N)..15

Dependencies:
    - None beyond stdlib + pydaw.model.midi
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MPE Configuration
# ---------------------------------------------------------------------------

@dataclass
class MPEZoneConfig:
    """Configuration for one MPE zone (Lower or Upper).

    pitch_bend_range: semitones for per-note pitch bend (typically 48 for MPE,
                      but some controllers use 24 or 96).
    member_channels: number of member channels (1..15).
    enabled: whether this zone is active.
    """
    enabled: bool = False
    member_channels: int = 15   # 1..15 (how many channels allocated)
    pitch_bend_range: int = 48  # semitones
    pressure_enabled: bool = True
    slide_enabled: bool = True   # CC74 (Brightness / Slide)


@dataclass
class MPEConfig:
    """Complete MPE configuration for a track.

    Serializable via dataclasses.asdict() for project persistence.
    """
    mpe_enabled: bool = False
    lower_zone: MPEZoneConfig = field(default_factory=lambda: MPEZoneConfig(
        enabled=True, member_channels=15, pitch_bend_range=48))
    upper_zone: MPEZoneConfig = field(default_factory=lambda: MPEZoneConfig(
        enabled=False, member_channels=0, pitch_bend_range=48))

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict."""
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MPEConfig":
        """Deserialize from dict."""
        if not isinstance(d, dict):
            return cls()
        try:
            cfg = cls(
                mpe_enabled=bool(d.get("mpe_enabled", False)),
            )
            lz = d.get("lower_zone", {})
            if isinstance(lz, dict):
                cfg.lower_zone = MPEZoneConfig(
                    enabled=bool(lz.get("enabled", True)),
                    member_channels=max(0, min(15, int(lz.get("member_channels", 15)))),
                    pitch_bend_range=max(1, min(96, int(lz.get("pitch_bend_range", 48)))),
                    pressure_enabled=bool(lz.get("pressure_enabled", True)),
                    slide_enabled=bool(lz.get("slide_enabled", True)),
                )
            uz = d.get("upper_zone", {})
            if isinstance(uz, dict):
                cfg.upper_zone = MPEZoneConfig(
                    enabled=bool(uz.get("enabled", False)),
                    member_channels=max(0, min(15, int(uz.get("member_channels", 0)))),
                    pitch_bend_range=max(1, min(96, int(uz.get("pitch_bend_range", 48)))),
                    pressure_enabled=bool(uz.get("pressure_enabled", True)),
                    slide_enabled=bool(uz.get("slide_enabled", True)),
                )
            return cfg
        except Exception:
            return cls()


# ---------------------------------------------------------------------------
# MPE Channel Allocator
# ---------------------------------------------------------------------------

class MPEChannelAllocator:
    """Allocates MIDI channels to notes in round-robin fashion.

    Each note-on gets its own MIDI channel from the zone's member channels.
    When a note-off arrives, its channel is released back to the pool.

    This is the core mechanism that enables per-note pitch bend, pressure,
    and slide in MPE.
    """

    def __init__(self, zone: MPEZoneConfig, is_lower: bool = True):
        self._zone = zone
        self._is_lower = is_lower

        # Build channel pool
        if is_lower:
            # Lower zone: manager = ch 1, members = ch 2..N
            self._manager_ch = 0  # 0-indexed
            n = min(15, max(1, zone.member_channels))
            self._member_channels = list(range(1, 1 + n))
        else:
            # Upper zone: manager = ch 16, members = ch (16-N)..15
            self._manager_ch = 15  # 0-indexed
            n = min(15, max(1, zone.member_channels))
            self._member_channels = list(range(15 - n, 15))

        # Channel allocation state
        self._free_channels: List[int] = list(self._member_channels)
        self._note_to_channel: Dict[int, int] = {}  # pitch -> channel
        self._channel_to_note: Dict[int, int] = {}  # channel -> pitch
        self._round_robin_idx = 0

    @property
    def manager_channel(self) -> int:
        return self._manager_ch

    @property
    def member_channels(self) -> List[int]:
        return list(self._member_channels)

    def is_member_channel(self, channel: int) -> bool:
        """Check if channel is a member channel of this zone."""
        return int(channel) in self._member_channels

    def is_manager_channel(self, channel: int) -> bool:
        """Check if channel is the manager channel of this zone."""
        return int(channel) == self._manager_ch

    def allocate_channel(self, pitch: int) -> int:
        """Allocate a member channel for a new note.

        Returns the channel (0-indexed) or -1 if no channels available.
        """
        p = int(pitch)
        # If note already has a channel, return it
        if p in self._note_to_channel:
            return self._note_to_channel[p]

        if not self._free_channels:
            # Steal oldest channel (voice stealing)
            if self._member_channels:
                ch = self._member_channels[self._round_robin_idx % len(self._member_channels)]
                self._round_robin_idx += 1
                # Release old note on this channel
                old_pitch = self._channel_to_note.pop(ch, None)
                if old_pitch is not None:
                    self._note_to_channel.pop(old_pitch, None)
            else:
                return -1
        else:
            ch = self._free_channels.pop(0)

        self._note_to_channel[p] = ch
        self._channel_to_note[ch] = p
        return ch

    def release_channel(self, pitch: int) -> int:
        """Release the channel for a note-off.

        Returns the channel that was released, or -1 if not found.
        """
        p = int(pitch)
        ch = self._note_to_channel.pop(p, None)
        if ch is None:
            return -1
        self._channel_to_note.pop(ch, None)
        self._free_channels.append(ch)
        return ch

    def get_channel_for_note(self, pitch: int) -> int:
        """Get the currently allocated channel for a note, or -1."""
        return self._note_to_channel.get(int(pitch), -1)

    def get_note_for_channel(self, channel: int) -> int:
        """Get the note currently on a channel, or -1."""
        return self._channel_to_note.get(int(channel), -1)

    def reset(self) -> None:
        """Reset all allocations."""
        self._free_channels = list(self._member_channels)
        self._note_to_channel.clear()
        self._channel_to_note.clear()
        self._round_robin_idx = 0


# ---------------------------------------------------------------------------
# MPE Processor
# ---------------------------------------------------------------------------

@dataclass
class MPENoteState:
    """Live state of an MPE note (pitch bend, pressure, slide)."""
    pitch: int = 60
    channel: int = 0
    velocity: int = 100
    # Per-note continuous controllers
    pitch_bend: float = 0.0      # -1.0 .. +1.0 (raw, before range scaling)
    pitch_bend_semitones: float = 0.0  # scaled by pitch_bend_range
    pressure: float = 0.0        # 0.0 .. 1.0 (channel aftertouch)
    slide: float = 0.5           # 0.0 .. 1.0 (CC74, default 0.5 = center)
    # Accumulated expression curves (for recording into MidiNote.expressions)
    pitch_bend_curve: List[Tuple[float, float]] = field(default_factory=list)
    pressure_curve: List[Tuple[float, float]] = field(default_factory=list)
    slide_curve: List[Tuple[float, float]] = field(default_factory=list)
    start_time: float = 0.0      # timestamp of note-on


class MPEProcessor:
    """Processes incoming MIDI messages and routes MPE data per-note.

    Converts multi-channel MPE input into per-note expression data
    that can be stored in MidiNote.expressions.

    Usage:
        proc = MPEProcessor(config)
        proc.process_midi_event(status, data1, data2, channel, timestamp)
        # ... query per-note state ...
        states = proc.get_active_notes()
    """

    def __init__(self, config: Optional[MPEConfig] = None):
        self._config = config or MPEConfig()
        self._lower_alloc: Optional[MPEChannelAllocator] = None
        self._upper_alloc: Optional[MPEChannelAllocator] = None
        self._active_notes: Dict[int, MPENoteState] = {}  # pitch -> state
        self._setup_allocators()

    def _setup_allocators(self) -> None:
        """Create channel allocators based on config."""
        cfg = self._config
        if cfg.mpe_enabled and cfg.lower_zone.enabled:
            self._lower_alloc = MPEChannelAllocator(cfg.lower_zone, is_lower=True)
        else:
            self._lower_alloc = None
        if cfg.mpe_enabled and cfg.upper_zone.enabled:
            self._upper_alloc = MPEChannelAllocator(cfg.upper_zone, is_lower=False)
        else:
            self._upper_alloc = None

    def set_config(self, config: MPEConfig) -> None:
        """Update MPE configuration."""
        self._config = config
        self._setup_allocators()
        self.reset()

    @property
    def is_mpe_enabled(self) -> bool:
        return self._config.mpe_enabled

    def process_note_on(self, channel: int, pitch: int, velocity: int,
                        timestamp: float = 0.0) -> Optional[MPENoteState]:
        """Process a note-on event.

        Returns the MPENoteState for the new note, or None if filtered.
        """
        if not self._config.mpe_enabled:
            return None

        # Determine which zone this belongs to
        zone, alloc = self._find_zone(int(channel))
        if alloc is None:
            return None

        # Allocate channel
        ch = alloc.allocate_channel(int(pitch))
        if ch < 0:
            return None

        state = MPENoteState(
            pitch=int(pitch),
            channel=ch,
            velocity=int(velocity),
            start_time=float(timestamp),
        )
        self._active_notes[int(pitch)] = state
        return state

    def process_note_off(self, channel: int, pitch: int,
                         timestamp: float = 0.0) -> Optional[MPENoteState]:
        """Process a note-off event.

        Returns the final MPENoteState (with accumulated curves), or None.
        """
        if not self._config.mpe_enabled:
            return None

        state = self._active_notes.pop(int(pitch), None)
        if state is None:
            return None

        # Release channel
        zone, alloc = self._find_zone(int(channel))
        if alloc:
            alloc.release_channel(int(pitch))

        return state

    def process_pitch_bend(self, channel: int, value: int,
                           timestamp: float = 0.0) -> None:
        """Process a pitch bend message (per-channel → per-note in MPE).

        value: 0..16383, center = 8192
        """
        if not self._config.mpe_enabled:
            return

        zone, alloc = self._find_zone(int(channel))
        if alloc is None:
            return

        # Find which note is on this channel
        pitch = alloc.get_note_for_channel(int(channel))
        if pitch < 0:
            return

        state = self._active_notes.get(pitch)
        if state is None:
            return

        # Normalize pitch bend: -1.0 to +1.0
        normalized = (float(value) - 8192.0) / 8192.0
        state.pitch_bend = max(-1.0, min(1.0, normalized))

        # Scale by zone pitch bend range
        if zone:
            state.pitch_bend_semitones = state.pitch_bend * float(zone.pitch_bend_range)

        # Record curve point
        state.pitch_bend_curve.append((float(timestamp), state.pitch_bend_semitones))

    def process_channel_pressure(self, channel: int, value: int,
                                  timestamp: float = 0.0) -> None:
        """Process channel aftertouch (per-note pressure in MPE).

        value: 0..127
        """
        if not self._config.mpe_enabled:
            return

        zone, alloc = self._find_zone(int(channel))
        if alloc is None:
            return

        pitch = alloc.get_note_for_channel(int(channel))
        if pitch < 0:
            return

        state = self._active_notes.get(pitch)
        if state is None:
            return

        state.pressure = float(value) / 127.0
        state.pressure_curve.append((float(timestamp), state.pressure))

    def process_cc(self, channel: int, cc: int, value: int,
                   timestamp: float = 0.0) -> None:
        """Process a CC message.

        CC74 = Slide (Brightness) in MPE.
        """
        if not self._config.mpe_enabled:
            return
        if int(cc) != 74:  # Only CC74 = Slide
            return

        zone, alloc = self._find_zone(int(channel))
        if alloc is None:
            return

        pitch = alloc.get_note_for_channel(int(channel))
        if pitch < 0:
            return

        state = self._active_notes.get(pitch)
        if state is None:
            return

        state.slide = float(value) / 127.0
        state.slide_curve.append((float(timestamp), state.slide))

    def _find_zone(self, channel: int) -> Tuple[Optional[MPEZoneConfig],
                                                  Optional[MPEChannelAllocator]]:
        """Find which zone a MIDI channel belongs to."""
        ch = int(channel)
        if self._lower_alloc and (self._lower_alloc.is_member_channel(ch)
                                   or self._lower_alloc.is_manager_channel(ch)):
            return self._config.lower_zone, self._lower_alloc
        if self._upper_alloc and (self._upper_alloc.is_member_channel(ch)
                                   or self._upper_alloc.is_manager_channel(ch)):
            return self._config.upper_zone, self._upper_alloc
        return None, None

    def get_active_notes(self) -> Dict[int, MPENoteState]:
        """Return dict of currently active notes (pitch -> state)."""
        return dict(self._active_notes)

    def get_note_state(self, pitch: int) -> Optional[MPENoteState]:
        """Get current state for an active note."""
        return self._active_notes.get(int(pitch))

    def note_state_to_expressions(self, state: MPENoteState,
                                   note_duration: float) -> Dict[str, list]:
        """Convert accumulated MPENoteState curves to MidiNote.expressions format.

        Returns dict like {"micropitch": [...], "pressure": [...], "slide": [...]}.
        """
        result: Dict[str, list] = {}
        if not state:
            return result

        dur = max(0.001, float(note_duration))
        start = float(state.start_time)

        # Pitch bend → micropitch expression
        if state.pitch_bend_curve:
            pts = []
            for ts, val in state.pitch_bend_curve:
                t = max(0.0, min(1.0, (ts - start) / dur))
                pts.append({"t": t, "v": val})
            if pts:
                result["micropitch"] = pts

        # Pressure → pressure expression
        if state.pressure_curve:
            pts = []
            for ts, val in state.pressure_curve:
                t = max(0.0, min(1.0, (ts - start) / dur))
                pts.append({"t": t, "v": val})
            if pts:
                result["pressure"] = pts

        # Slide → slide expression (CC74)
        if state.slide_curve:
            pts = []
            for ts, val in state.slide_curve:
                t = max(0.0, min(1.0, (ts - start) / dur))
                pts.append({"t": t, "v": val})
            if pts:
                result["slide"] = pts

        return result

    def reset(self) -> None:
        """Reset all state (active notes, channel allocations)."""
        self._active_notes.clear()
        if self._lower_alloc:
            self._lower_alloc.reset()
        if self._upper_alloc:
            self._upper_alloc.reset()


# ---------------------------------------------------------------------------
# MPE MIDI Input Detector
# ---------------------------------------------------------------------------

def detect_mpe_from_mcm(data: bytes) -> Optional[MPEConfig]:
    """Detect MPE configuration from MCM (MPE Configuration Message).

    MCM is a special RPN message:
    - CC 101 = 0, CC 100 = 6 (RPN 0x0006 = MPE Configuration)
    - CC 6 = number of member channels

    Returns MPEConfig if detected, None otherwise.
    """
    # This is a simplified detector — in practice this would parse
    # a stream of MIDI bytes looking for the RPN sequence.
    # For now, provides the API shape that the MIDI service can call.
    return None


# ---------------------------------------------------------------------------
# Preset MPE Configs for known controllers
# ---------------------------------------------------------------------------

_KNOWN_MPE_CONTROLLERS: Dict[str, MPEConfig] = {
    "Roli Seaboard": MPEConfig(
        mpe_enabled=True,
        lower_zone=MPEZoneConfig(enabled=True, member_channels=15,
                                  pitch_bend_range=48),
    ),
    "Linnstrument": MPEConfig(
        mpe_enabled=True,
        lower_zone=MPEZoneConfig(enabled=True, member_channels=15,
                                  pitch_bend_range=48),
    ),
    "Sensel Morph": MPEConfig(
        mpe_enabled=True,
        lower_zone=MPEZoneConfig(enabled=True, member_channels=15,
                                  pitch_bend_range=48),
    ),
    "Haken Continuum": MPEConfig(
        mpe_enabled=True,
        lower_zone=MPEZoneConfig(enabled=True, member_channels=15,
                                  pitch_bend_range=96),
    ),
    "Ableton Push 3": MPEConfig(
        mpe_enabled=True,
        lower_zone=MPEZoneConfig(enabled=True, member_channels=15,
                                  pitch_bend_range=48),
    ),
}


def get_mpe_preset(controller_name: str) -> Optional[MPEConfig]:
    """Get preset MPE config for a known controller."""
    return _KNOWN_MPE_CONTROLLERS.get(str(controller_name))


def list_mpe_presets() -> List[str]:
    """Return list of known MPE controller names."""
    return list(_KNOWN_MPE_CONTROLLERS.keys())
