# -*- coding: utf-8 -*-
"""Multi-Sample Mapping data model for the Advanced Sampler.

v0.0.20.656 — AP7 Phase 7A

Data structures:
- SampleZone: One sample mapped to key range + velocity range with per-zone DSP
- RoundRobinGroup: Cyclically selects from multiple zones for the same key/vel
- MultiSampleMap: Manages all zones, lookup by (note, velocity), serialization
"""

from __future__ import annotations

import copy
import logging
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


@dataclass
class LoopPoints:
    """Sample loop point definition."""
    enabled: bool = False
    start_norm: float = 0.0   # 0.0 .. 1.0 (normalized to sample length)
    end_norm: float = 1.0     # 0.0 .. 1.0
    crossfade_norm: float = 0.01  # crossfade length (normalized)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LoopPoints":
        return cls(
            enabled=bool(d.get("enabled", False)),
            start_norm=float(d.get("start_norm", 0.0)),
            end_norm=float(d.get("end_norm", 1.0)),
            crossfade_norm=float(d.get("crossfade_norm", 0.01)),
        )


@dataclass
class ZoneEnvelope:
    """ADSR envelope per sample zone."""
    attack: float = 0.005    # seconds
    hold: float = 0.0        # seconds
    decay: float = 0.15      # seconds
    sustain: float = 1.0     # 0.0 .. 1.0
    release: float = 0.20    # seconds

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ZoneEnvelope":
        return cls(
            attack=float(d.get("attack", 0.005)),
            hold=float(d.get("hold", 0.0)),
            decay=float(d.get("decay", 0.15)),
            sustain=float(d.get("sustain", 1.0)),
            release=float(d.get("release", 0.20)),
        )


@dataclass
class ZoneFilter:
    """Filter settings per sample zone."""
    filter_type: str = "off"    # off, lp, hp, bp
    cutoff_hz: float = 8000.0   # 20..20000
    resonance: float = 0.707    # Q: 0.25..12.0
    env_amount: float = 0.0     # -1.0..1.0 (filter envelope modulation)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ZoneFilter":
        return cls(
            filter_type=str(d.get("filter_type", "off")),
            cutoff_hz=float(d.get("cutoff_hz", 8000.0)),
            resonance=float(d.get("resonance", 0.707)),
            env_amount=float(d.get("env_amount", 0.0)),
        )


@dataclass
class ModulationSlot:
    """Single modulation routing entry."""
    source: str = "none"       # none, lfo1, lfo2, env_amp, env_filter, velocity, key_track
    destination: str = "none"  # none, pitch, filter_cutoff, amp, pan
    amount: float = 0.0        # -1.0 .. 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ModulationSlot":
        return cls(
            source=str(d.get("source", "none")),
            destination=str(d.get("destination", "none")),
            amount=float(d.get("amount", 0.0)),
        )


@dataclass
class ZoneLFO:
    """LFO settings for modulation."""
    rate_hz: float = 1.0       # 0.01 .. 50.0
    shape: str = "sine"        # sine, triangle, square, saw, random
    sync: bool = False         # tempo-sync
    sync_rate: str = "1/4"     # beat division when synced

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ZoneLFO":
        return cls(
            rate_hz=float(d.get("rate_hz", 1.0)),
            shape=str(d.get("shape", "sine")),
            sync=bool(d.get("sync", False)),
            sync_rate=str(d.get("sync_rate", "1/4")),
        )


@dataclass
class SampleZone:
    """A single sample zone in a multi-sample map.

    Maps a sample file to a key range + velocity range with per-zone DSP.
    """
    # Identity
    zone_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""

    # Sample reference
    sample_path: str = ""
    sample_media_id: str = ""   # project-relative media ID

    # Key mapping
    key_low: int = 0            # MIDI note 0..127
    key_high: int = 127         # MIDI note 0..127
    root_note: int = 60         # MIDI note that plays at original pitch
    velocity_low: int = 0       # 0..127
    velocity_high: int = 127    # 0..127

    # Playback
    sample_start: float = 0.0   # normalized 0..1
    sample_end: float = 1.0     # normalized 0..1
    loop: LoopPoints = field(default_factory=LoopPoints)

    # Per-zone DSP
    gain: float = 0.8           # 0.0..1.0
    pan: float = 0.0            # -1.0..1.0
    tune_semitones: float = 0.0  # -24..24
    tune_cents: float = 0.0     # -100..100

    # Envelope + Filter
    amp_envelope: ZoneEnvelope = field(default_factory=ZoneEnvelope)
    filter: ZoneFilter = field(default_factory=ZoneFilter)
    filter_envelope: ZoneEnvelope = field(default_factory=lambda: ZoneEnvelope(
        attack=0.005, hold=0.0, decay=0.3, sustain=0.0, release=0.1
    ))

    # Modulation
    lfo1: ZoneLFO = field(default_factory=ZoneLFO)
    lfo2: ZoneLFO = field(default_factory=lambda: ZoneLFO(rate_hz=0.5, shape="triangle"))
    mod_slots: List[ModulationSlot] = field(default_factory=lambda: [
        ModulationSlot() for _ in range(4)
    ])

    # Round-robin
    rr_group: int = 0           # 0 = no round-robin, 1+ = RR group ID

    # Visual
    color: str = "#4488cc"

    def contains(self, note: int, velocity: int) -> bool:
        """Check if this zone responds to the given note + velocity."""
        return (self.key_low <= note <= self.key_high and
                self.velocity_low <= velocity <= self.velocity_high)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "zone_id": self.zone_id,
            "name": self.name,
            "sample_path": self.sample_path,
            "sample_media_id": self.sample_media_id,
            "key_low": self.key_low,
            "key_high": self.key_high,
            "root_note": self.root_note,
            "velocity_low": self.velocity_low,
            "velocity_high": self.velocity_high,
            "sample_start": self.sample_start,
            "sample_end": self.sample_end,
            "loop": self.loop.to_dict(),
            "gain": self.gain,
            "pan": self.pan,
            "tune_semitones": self.tune_semitones,
            "tune_cents": self.tune_cents,
            "amp_envelope": self.amp_envelope.to_dict(),
            "filter": self.filter.to_dict(),
            "filter_envelope": self.filter_envelope.to_dict(),
            "lfo1": self.lfo1.to_dict(),
            "lfo2": self.lfo2.to_dict(),
            "mod_slots": [m.to_dict() for m in self.mod_slots],
            "rr_group": self.rr_group,
            "color": self.color,
        }
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SampleZone":
        zone = cls(
            zone_id=str(d.get("zone_id", uuid.uuid4().hex[:12])),
            name=str(d.get("name", "")),
            sample_path=str(d.get("sample_path", "")),
            sample_media_id=str(d.get("sample_media_id", "")),
            key_low=int(d.get("key_low", 0)),
            key_high=int(d.get("key_high", 127)),
            root_note=int(d.get("root_note", 60)),
            velocity_low=int(d.get("velocity_low", 0)),
            velocity_high=int(d.get("velocity_high", 127)),
            sample_start=float(d.get("sample_start", 0.0)),
            sample_end=float(d.get("sample_end", 1.0)),
            gain=float(d.get("gain", 0.8)),
            pan=float(d.get("pan", 0.0)),
            tune_semitones=float(d.get("tune_semitones", 0.0)),
            tune_cents=float(d.get("tune_cents", 0.0)),
            rr_group=int(d.get("rr_group", 0)),
            color=str(d.get("color", "#4488cc")),
        )
        lp = d.get("loop")
        if isinstance(lp, dict):
            zone.loop = LoopPoints.from_dict(lp)
        ae = d.get("amp_envelope")
        if isinstance(ae, dict):
            zone.amp_envelope = ZoneEnvelope.from_dict(ae)
        ff = d.get("filter")
        if isinstance(ff, dict):
            zone.filter = ZoneFilter.from_dict(ff)
        fe = d.get("filter_envelope")
        if isinstance(fe, dict):
            zone.filter_envelope = ZoneEnvelope.from_dict(fe)
        l1 = d.get("lfo1")
        if isinstance(l1, dict):
            zone.lfo1 = ZoneLFO.from_dict(l1)
        l2 = d.get("lfo2")
        if isinstance(l2, dict):
            zone.lfo2 = ZoneLFO.from_dict(l2)
        ms = d.get("mod_slots")
        if isinstance(ms, list):
            zone.mod_slots = [ModulationSlot.from_dict(m) if isinstance(m, dict)
                              else ModulationSlot() for m in ms]
        return zone


class MultiSampleMap:
    """Manages a collection of SampleZones with key/velocity lookup and round-robin.

    Lookup: find_zones(note, velocity) returns matching zones.
    Round-robin: If multiple zones in the same RR group match, cycles through them.
    """

    def __init__(self) -> None:
        self.zones: List[SampleZone] = []
        self._rr_counters: Dict[int, int] = {}  # rr_group -> current index

    def add_zone(self, zone: SampleZone) -> None:
        """Add a zone to the map."""
        self.zones.append(zone)

    def remove_zone(self, zone_id: str) -> Optional[SampleZone]:
        """Remove a zone by ID. Returns removed zone or None."""
        for i, z in enumerate(self.zones):
            if z.zone_id == zone_id:
                return self.zones.pop(i)
        return None

    def get_zone(self, zone_id: str) -> Optional[SampleZone]:
        """Get zone by ID."""
        for z in self.zones:
            if z.zone_id == zone_id:
                return z
        return None

    def find_zones(self, note: int, velocity: int) -> List[SampleZone]:
        """Find all zones matching the given note + velocity.

        Handles round-robin: if multiple zones with the same rr_group match,
        only the next one in the cycle is returned.
        """
        matches: List[SampleZone] = []
        rr_buckets: Dict[int, List[SampleZone]] = {}

        for z in self.zones:
            if z.contains(note, velocity):
                if z.rr_group > 0:
                    rr_buckets.setdefault(z.rr_group, []).append(z)
                else:
                    matches.append(z)

        # Resolve round-robin groups
        for grp, bucket in rr_buckets.items():
            if not bucket:
                continue
            idx = self._rr_counters.get(grp, 0) % len(bucket)
            matches.append(bucket[idx])
            self._rr_counters[grp] = idx + 1

        return matches

    def reset_round_robin(self) -> None:
        """Reset all round-robin counters."""
        self._rr_counters.clear()

    def clear(self) -> None:
        """Remove all zones."""
        self.zones.clear()
        self._rr_counters.clear()

    def duplicate_zone(self, zone_id: str) -> Optional[SampleZone]:
        """Duplicate a zone, returning the new copy."""
        src = self.get_zone(zone_id)
        if src is None:
            return None
        new = SampleZone.from_dict(src.to_dict())
        new.zone_id = uuid.uuid4().hex[:12]
        new.name = f"{src.name} (copy)" if src.name else "Zone (copy)"
        self.zones.append(new)
        return new

    def to_dict(self) -> Dict[str, Any]:
        return {
            "zones": [z.to_dict() for z in self.zones],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MultiSampleMap":
        m = cls()
        for zd in d.get("zones", []):
            if isinstance(zd, dict):
                try:
                    m.zones.append(SampleZone.from_dict(zd))
                except Exception:
                    log.warning("Failed to load zone: %s", zd.get("zone_id", "?"))
        return m


# ----- Note name utilities -----
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_NOTE_NAMES_DE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "H"]


def midi_note_name(note: int, german: bool = False) -> str:
    """Convert MIDI note number to name (e.g., 60 -> 'C4')."""
    if note < 0 or note > 127:
        return "?"
    names = _NOTE_NAMES_DE if german else _NOTE_NAMES
    octave = (note // 12) - 1
    return f"{names[note % 12]}{octave}"


def note_name_to_midi(name: str) -> int:
    """Convert note name like 'C4' or 'C#3' to MIDI number. Returns -1 on failure."""
    try:
        name = name.strip()
        if not name:
            return -1
        # Parse note name and octave
        if len(name) >= 3 and name[1] == '#':
            nn = name[:2]
            octave = int(name[2:])
        elif len(name) >= 3 and name[1] == 'b':
            # Flat: convert to sharp equivalent
            flat_idx = _NOTE_NAMES.index(name[0])
            nn = _NOTE_NAMES[(flat_idx - 1) % 12]
            octave = int(name[2:])
        else:
            nn = name[0]
            if nn == 'H':
                nn = 'B'
            octave = int(name[1:])
        idx = _NOTE_NAMES.index(nn) if nn in _NOTE_NAMES else _NOTE_NAMES_DE.index(nn)
        return (octave + 1) * 12 + idx
    except (ValueError, IndexError):
        return -1


# Zone color palette for visual distinction
ZONE_COLORS = [
    "#4488cc", "#cc4488", "#44cc88", "#cc8844",
    "#8844cc", "#88cc44", "#44cccc", "#cc4444",
    "#4444cc", "#44cc44", "#cccc44", "#cc44cc",
]


def next_zone_color(existing_count: int) -> str:
    """Get next zone color from palette."""
    return ZONE_COLORS[existing_count % len(ZONE_COLORS)]
