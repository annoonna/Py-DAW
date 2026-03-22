# -*- coding: utf-8 -*-
"""Auto-Mapping utilities for the Multi-Sample Sampler.

v0.0.20.656 — AP7 Phase 7A

Provides:
- Chromatic auto-mapping: maps samples to consecutive keys
- Drum auto-mapping: maps samples to GM drum note assignments
- Filename pattern detection: C3.wav, Kick.wav, etc.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

from .multisample_model import (
    SampleZone, MultiSampleMap, ZoneEnvelope, midi_note_name,
    note_name_to_midi, next_zone_color,
)

log = logging.getLogger(__name__)


# --- GM Drum Map (MIDI note -> name) ---
_GM_DRUM_MAP = {
    35: "Acoustic Bass Drum", 36: "Bass Drum 1", 37: "Side Stick",
    38: "Acoustic Snare", 39: "Hand Clap", 40: "Electric Snare",
    41: "Low Floor Tom", 42: "Closed Hi-Hat", 43: "High Floor Tom",
    44: "Pedal Hi-Hat", 45: "Low Tom", 46: "Open Hi-Hat",
    47: "Low-Mid Tom", 48: "Hi-Mid Tom", 49: "Crash Cymbal 1",
    50: "High Tom", 51: "Ride Cymbal 1", 52: "Chinese Cymbal",
    53: "Ride Bell", 54: "Tambourine", 55: "Splash Cymbal",
    56: "Cowbell", 57: "Crash Cymbal 2", 58: "Vibraslap",
    59: "Ride Cymbal 2", 60: "Hi Bongo", 61: "Low Bongo",
    62: "Mute Hi Conga", 63: "Open Hi Conga", 64: "Low Conga",
    65: "High Timbale", 66: "Low Timbale", 67: "High Agogo",
    68: "Low Agogo", 69: "Cabasa", 70: "Maracas",
    71: "Short Whistle", 72: "Long Whistle", 73: "Short Guiro",
    74: "Long Guiro", 75: "Claves", 76: "Hi Wood Block",
    77: "Low Wood Block", 78: "Mute Cuica", 79: "Open Cuica",
    80: "Mute Triangle", 81: "Open Triangle",
}

# Keyword patterns for drum sound detection
_DRUM_KEYWORDS = {
    "kick": 36, "bass drum": 36, "bassdrum": 36, "bd": 36,
    "snare": 38, "sn": 38, "sd": 38,
    "clap": 39, "cp": 39, "handclap": 39,
    "hat": 42, "hihat": 42, "hh": 42, "hi-hat": 42,
    "open hat": 46, "open hihat": 46, "oh": 46, "open hh": 46,
    "closed hat": 42, "closed hihat": 42, "ch": 42, "closed hh": 42,
    "pedal hat": 44, "pedal hihat": 44, "ph": 44,
    "tom": 47, "low tom": 41, "mid tom": 47, "high tom": 50, "hi tom": 50,
    "floor tom": 41,
    "ride": 51, "crash": 49, "cymbal": 49, "china": 52, "splash": 55,
    "rim": 37, "rimshot": 37, "sidestick": 37, "side stick": 37,
    "tambourine": 54, "tamb": 54,
    "cowbell": 56, "cbell": 56,
    "bongo": 60, "conga": 63,
    "perc": 56, "shaker": 70, "maracas": 70,
}


def _extract_note_from_filename(filename: str) -> int:
    """Try to extract a MIDI note number from a filename.

    Patterns matched:
    - C4.wav, C#3.wav, Bb2.wav
    - 060.wav, note_60.wav, midi_60.wav
    - Piano_C4_vel100.wav

    Returns -1 if no note found.
    """
    stem = Path(filename).stem

    # Pattern 1: Note name at start or after separator
    # Match C4, C#4, Db3, etc.
    m = re.search(r'(?:^|[_\-\s])([A-Ga-g][#b]?\d)', stem)
    if m:
        note_str = m.group(1).upper()
        midi = note_name_to_midi(note_str)
        if 0 <= midi <= 127:
            return midi

    # Pattern 2: Pure number that could be MIDI note
    m = re.search(r'(?:^|[_\-\s]|note|midi)[\s_\-]?(\d{1,3})(?:[_\-\s]|$)', stem, re.IGNORECASE)
    if m:
        num = int(m.group(1))
        if 0 <= num <= 127:
            return num

    return -1


def _extract_velocity_from_filename(filename: str) -> Tuple[int, int]:
    """Try to extract velocity info from filename.

    Returns (vel_low, vel_high). Default (0, 127).
    """
    stem = Path(filename).stem.lower()

    # Pattern: vel100, v100, velocity_100
    m = re.search(r'(?:vel|velocity|v)[\s_\-]?(\d{1,3})', stem)
    if m:
        v = min(127, int(m.group(1)))
        return (max(0, v - 15), min(127, v + 15))

    # Layers: pp, p, mp, mf, f, ff
    layers = {"ppp": (0, 20), "pp": (0, 40), "p": (21, 60),
              "mp": (41, 80), "mf": (61, 100), "f": (81, 110),
              "ff": (101, 127), "fff": (111, 127)}
    for key, (lo, hi) in sorted(layers.items(), key=lambda x: -len(x[0])):
        if re.search(rf'(?:^|[_\-\s]){re.escape(key)}(?:[_\-\s]|$)', stem):
            return (lo, hi)

    return (0, 127)


def _detect_drum_note(filename: str) -> int:
    """Try to detect drum type from filename keywords.

    Returns GM drum MIDI note or -1.
    """
    stem = Path(filename).stem.lower().replace("_", " ").replace("-", " ")

    # Check all keyword patterns (longer matches first)
    for keyword, note in sorted(_DRUM_KEYWORDS.items(), key=lambda x: -len(x[0])):
        if keyword in stem:
            return note

    return -1


def auto_map_chromatic(files: List[str], root_note: int = 60,
                       key_spread: int = 1) -> MultiSampleMap:
    """Auto-map a list of sample files chromatically.

    If filenames contain note info (C4.wav), uses that.
    Otherwise maps sequentially starting from root_note.

    Args:
        files: List of audio file paths
        root_note: Starting MIDI note for sequential mapping
        key_spread: Number of keys per sample (for spreading)

    Returns:
        MultiSampleMap with created zones
    """
    sample_map = MultiSampleMap()

    # First pass: detect notes from filenames
    detected: List[Tuple[str, int, int, int]] = []  # (path, note, vel_lo, vel_hi)
    undetected: List[str] = []

    for f in sorted(files):
        note = _extract_note_from_filename(f)
        vel_lo, vel_hi = _extract_velocity_from_filename(f)
        if note >= 0:
            detected.append((f, note, vel_lo, vel_hi))
        else:
            undetected.append(f)

    # Map detected files
    for i, (path, note, vel_lo, vel_hi) in enumerate(detected):
        zone = SampleZone(
            name=Path(path).stem,
            sample_path=str(path),
            root_note=note,
            key_low=max(0, note - key_spread // 2),
            key_high=min(127, note + key_spread // 2),
            velocity_low=vel_lo,
            velocity_high=vel_hi,
            color=next_zone_color(i),
        )
        sample_map.add_zone(zone)

    # Map undetected files sequentially
    current_note = root_note
    for i, path in enumerate(undetected):
        zone = SampleZone(
            name=Path(path).stem,
            sample_path=str(path),
            root_note=current_note,
            key_low=max(0, current_note - key_spread // 2),
            key_high=min(127, current_note + key_spread // 2),
            color=next_zone_color(len(detected) + i),
        )
        sample_map.add_zone(zone)
        current_note += key_spread

    # Adjust overlapping key ranges
    _resolve_key_overlaps(sample_map)

    return sample_map


def auto_map_drum(files: List[str]) -> MultiSampleMap:
    """Auto-map sample files to GM drum notes based on filename keywords.

    Files that can't be mapped are assigned to sequential notes starting from C1.
    """
    sample_map = MultiSampleMap()
    used_notes: set = set()
    undetected: List[str] = []

    for i, f in enumerate(sorted(files)):
        note = _detect_drum_note(f)
        if note >= 0:
            # Resolve conflicts: if note already used, try nearby
            while note in used_notes and note < 81:
                note += 1
            zone = SampleZone(
                name=Path(f).stem,
                sample_path=str(f),
                root_note=note,
                key_low=note,
                key_high=note,
                color=next_zone_color(i),
                # Drum-typical: short envelope
                amp_envelope=ZoneEnvelope(
                    attack=0.001, hold=0.0, decay=0.5, sustain=0.0, release=0.05
                ),
            )
            sample_map.add_zone(zone)
            used_notes.add(note)
        else:
            undetected.append(f)

    # Assign undetected to C1 (36) upward
    next_note = 36
    for i, f in enumerate(undetected):
        while next_note in used_notes and next_note < 127:
            next_note += 1
        if next_note > 127:
            break
        zone = SampleZone(
            name=Path(f).stem,
            sample_path=str(f),
            root_note=next_note,
            key_low=next_note,
            key_high=next_note,
            color=next_zone_color(len(used_notes) + i),
        )
        sample_map.add_zone(zone)
        used_notes.add(next_note)
        next_note += 1

    return sample_map


def auto_map_velocity_layers(files: List[str], note: int = 60,
                             key_spread: int = 1) -> MultiSampleMap:
    """Map multiple files as velocity layers on the same note.

    Files are sorted alphabetically and spread across the velocity range.
    """
    sample_map = MultiSampleMap()
    n = len(files)
    if n == 0:
        return sample_map

    vel_step = max(1, 127 // n)

    for i, f in enumerate(sorted(files)):
        vel_lo = i * vel_step
        vel_hi = min(127, (i + 1) * vel_step - 1) if i < n - 1 else 127

        zone = SampleZone(
            name=Path(f).stem,
            sample_path=str(f),
            root_note=note,
            key_low=max(0, note - key_spread // 2),
            key_high=min(127, note + key_spread // 2),
            velocity_low=vel_lo,
            velocity_high=vel_hi,
            color=next_zone_color(i),
        )
        sample_map.add_zone(zone)

    return sample_map


def auto_map_round_robin(files: List[str], note: int = 60,
                         key_spread: int = 1, rr_group: int = 1) -> MultiSampleMap:
    """Map multiple files as round-robin alternatives on the same note/velocity."""
    sample_map = MultiSampleMap()

    for i, f in enumerate(sorted(files)):
        zone = SampleZone(
            name=Path(f).stem,
            sample_path=str(f),
            root_note=note,
            key_low=max(0, note - key_spread // 2),
            key_high=min(127, note + key_spread // 2),
            rr_group=rr_group,
            color=next_zone_color(i),
        )
        sample_map.add_zone(zone)

    return sample_map


def _resolve_key_overlaps(sample_map: MultiSampleMap) -> None:
    """Adjust zone key ranges to avoid unintended overlaps.

    Simple strategy: sort by root_note, split ranges at midpoints.
    Only adjusts zones in the same velocity range.
    """
    zones = sorted(sample_map.zones, key=lambda z: z.root_note)
    for i in range(len(zones) - 1):
        a, b = zones[i], zones[i + 1]
        # Only adjust if velocity ranges overlap
        if a.velocity_low <= b.velocity_high and b.velocity_low <= a.velocity_high:
            if a.key_high >= b.key_low:
                mid = (a.root_note + b.root_note) // 2
                a.key_high = mid
                b.key_low = mid + 1


__all__ = [
    "auto_map_chromatic", "auto_map_drum",
    "auto_map_velocity_layers", "auto_map_round_robin",
]
