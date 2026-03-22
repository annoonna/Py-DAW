# -*- coding: utf-8 -*-
"""Groove Template System (AP6 Phase 6C).

v0.0.20.644: Groove templates for timing and velocity manipulation.

Features:
- Factory groove library (Swing, MPC, TR-808, Live-Drummer, etc.)
- Extract groove from existing MIDI clips
- Apply groove to any MIDI note list with adjustable amount (0-100%)
- Humanize function: random timing/velocity variation

Groove Template Format:
{
    "name": "MPC Swing 60%",
    "category": "MPC",
    "grid_beats": 0.25,    # grid resolution (1/16 note)
    "steps": 16,           # number of steps per cycle
    "timing": [0.0, ...],  # timing offset per step (in beats, ± from grid)
    "velocity": [1.0, ...], # velocity multiplier per step (0..2)
    "length": [1.0, ...],  # length multiplier per step (0..2)
}

All three arrays (timing, velocity, length) cycle modulo steps.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Tuple


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(float(lo), min(float(hi), float(v)))


# ---------------------------------------------------------------------------
# Factory Groove Templates
# ---------------------------------------------------------------------------

def _make_swing(name: str, category: str, swing_pct: float, steps: int = 16,
                grid: float = 0.25) -> Dict[str, Any]:
    """Generate a swing groove. swing_pct: 0=straight, 100=full triplet."""
    # Swing shifts every other step forward
    # At 50%: straight. At 66.7%: triplet. At 100%: max dotted feel.
    shift = (swing_pct / 100.0) * grid * 0.5  # max half-grid shift
    timing = []
    velocity = []
    length = []
    for i in range(steps):
        if i % 2 == 1:
            timing.append(shift)
        else:
            timing.append(0.0)
        velocity.append(1.0)
        length.append(1.0)
    return {
        "name": name,
        "category": category,
        "grid_beats": grid,
        "steps": steps,
        "timing": timing,
        "velocity": velocity,
        "length": length,
    }


def _mpc_groove(swing_pct: float) -> Dict[str, Any]:
    """MPC-style groove: swing + accent pattern + ghost notes."""
    g = _make_swing(f"MPC Swing {int(swing_pct)}%", "MPC", swing_pct)
    # MPC accent: beat 1 strong, beat 3 medium, off-beats softer
    vel_pattern = [
        1.0, 0.7, 0.85, 0.65,  # beat 1
        0.95, 0.68, 0.82, 0.62,  # beat 2
        0.98, 0.72, 0.88, 0.66,  # beat 3
        0.92, 0.6, 0.78, 0.58,  # beat 4
    ]
    g["velocity"] = vel_pattern[:g["steps"]]
    return g


def _tr808_groove() -> Dict[str, Any]:
    """TR-808 straight grid with subtle machine-like velocity variation."""
    steps = 16
    timing = [0.0] * steps
    # 808: very slight random-ish timing (machine jitter ~0.5ms at 120 BPM)
    jitter_beats = 0.002  # barely perceptible
    rng = random.Random(808)
    timing = [rng.uniform(-jitter_beats, jitter_beats) for _ in range(steps)]
    velocity = []
    for i in range(steps):
        if i % 4 == 0:
            velocity.append(1.0)  # downbeat accent
        elif i % 2 == 0:
            velocity.append(0.9)  # 8th notes
        else:
            velocity.append(0.75)  # 16ths
    length = [1.0] * steps
    return {
        "name": "TR-808",
        "category": "Machine",
        "grid_beats": 0.25,
        "steps": steps,
        "timing": timing,
        "velocity": velocity,
        "length": length,
    }


def _live_drummer_groove(style: str = "rock") -> Dict[str, Any]:
    """Human drummer groove with natural feel."""
    steps = 16
    rng = random.Random(hash(style) & 0xFFFFFFFF)

    if style == "rock":
        # Rock: behind the beat, strong accents on 2 and 4
        timing = []
        velocity = []
        for i in range(steps):
            # Slightly behind (positive = late)
            base_lag = 0.008 + rng.gauss(0, 0.004)
            if i % 4 == 0:  # downbeats
                timing.append(base_lag * 0.5)
                velocity.append(0.95 + rng.gauss(0, 0.03))
            elif i % 4 == 2:  # upbeats (snare on 2/4)
                timing.append(base_lag * 0.3)
                velocity.append(1.0 + rng.gauss(0, 0.02))
            elif i % 2 == 1:  # 8th note off-beats
                timing.append(base_lag + rng.gauss(0, 0.006))
                velocity.append(0.7 + rng.gauss(0, 0.05))
            else:
                timing.append(base_lag + rng.gauss(0, 0.005))
                velocity.append(0.82 + rng.gauss(0, 0.04))
        name = "Live Drummer (Rock)"
    elif style == "jazz":
        # Jazz: swing feel, softer dynamics
        timing = []
        velocity = []
        for i in range(steps):
            if i % 2 == 1:
                # Swing the off-beats
                timing.append(0.04 + rng.gauss(0, 0.008))
            else:
                timing.append(rng.gauss(0, 0.005))

            if i % 4 == 0:
                velocity.append(0.85 + rng.gauss(0, 0.04))
            elif i % 4 == 2:
                velocity.append(0.78 + rng.gauss(0, 0.05))
            else:
                velocity.append(0.6 + rng.gauss(0, 0.06))
        name = "Live Drummer (Jazz)"
    elif style == "hiphop":
        # Hip-hop: laid back, heavy on 1 and 3
        timing = []
        velocity = []
        for i in range(steps):
            lag = 0.012 + rng.gauss(0, 0.005)  # behind the beat
            if i % 2 == 1:
                lag += 0.02 + rng.gauss(0, 0.008)  # extra swing on off-beats
            timing.append(lag)

            if i % 8 == 0:
                velocity.append(1.0 + rng.gauss(0, 0.02))
            elif i % 4 == 0:
                velocity.append(0.92 + rng.gauss(0, 0.03))
            elif i % 2 == 0:
                velocity.append(0.75 + rng.gauss(0, 0.04))
            else:
                velocity.append(0.6 + rng.gauss(0, 0.06))
        name = "Live Drummer (Hip-Hop)"
    else:
        timing = [rng.gauss(0, 0.005) for _ in range(steps)]
        velocity = [0.85 + rng.gauss(0, 0.05) for _ in range(steps)]
        name = f"Live Drummer ({style.title()})"

    # Clamp values
    velocity = [_clamp(v, 0.3, 1.2) for v in velocity]
    length = [1.0 + rng.gauss(0, 0.05) for _ in range(steps)]
    length = [_clamp(l, 0.7, 1.3) for l in length]

    return {
        "name": name,
        "category": "Drummer",
        "grid_beats": 0.25,
        "steps": steps,
        "timing": timing,
        "velocity": velocity,
        "length": length,
    }


def get_factory_grooves() -> List[Dict[str, Any]]:
    """Return all built-in groove templates."""
    return [
        _make_swing("Swing 50% (Straight)", "Swing", 0.0),
        _make_swing("Swing 55% (Light)", "Swing", 30.0),
        _make_swing("Swing 60% (Medium)", "Swing", 55.0),
        _make_swing("Swing 66% (Triplet)", "Swing", 80.0),
        _make_swing("Swing 70% (Heavy)", "Swing", 100.0),
        _mpc_groove(55.0),
        _mpc_groove(62.0),
        _mpc_groove(70.0),
        _tr808_groove(),
        _live_drummer_groove("rock"),
        _live_drummer_groove("jazz"),
        _live_drummer_groove("hiphop"),
    ]


# ---------------------------------------------------------------------------
# Extract Groove from MIDI Notes
# ---------------------------------------------------------------------------

def extract_groove_from_notes(notes: List[Any], grid_beats: float = 0.25,
                              steps: int = 16) -> Dict[str, Any]:
    """Extract a groove template from a list of MIDI notes.

    Analyzes timing offsets, velocities, and note lengths relative to a grid
    to create a reusable groove template.

    Args:
        notes: List of MidiNote-like objects (need .start_beats, .velocity, .length_beats)
        grid_beats: Grid resolution (default 0.25 = 16th notes)
        steps: Number of steps in the cycle

    Returns:
        Groove template dict
    """
    # Collect data per grid step
    step_timings: Dict[int, List[float]] = {i: [] for i in range(steps)}
    step_velocities: Dict[int, List[float]] = {i: [] for i in range(steps)}
    step_lengths: Dict[int, List[float]] = {i: [] for i in range(steps)}

    for n in notes:
        try:
            start = float(getattr(n, 'start_beats', 0.0))
            vel = int(getattr(n, 'velocity', 100))
            length = float(getattr(n, 'length_beats', 0.125))

            # Find nearest grid position
            grid_pos = round(start / grid_beats)
            quantized = grid_pos * grid_beats
            offset = start - quantized  # timing offset in beats

            step_idx = int(grid_pos) % steps

            step_timings[step_idx].append(offset)
            step_velocities[step_idx].append(float(vel))
            step_lengths[step_idx].append(length / grid_beats)  # normalize to grid
        except Exception:
            continue

    # Average the collected data
    timing = []
    velocity = []
    length = []
    for i in range(steps):
        if step_timings[i]:
            timing.append(sum(step_timings[i]) / len(step_timings[i]))
        else:
            timing.append(0.0)

        if step_velocities[i]:
            avg_vel = sum(step_velocities[i]) / len(step_velocities[i])
            velocity.append(avg_vel / 100.0)  # normalize: 100 → 1.0
        else:
            velocity.append(1.0)

        if step_lengths[i]:
            length.append(sum(step_lengths[i]) / len(step_lengths[i]))
        else:
            length.append(1.0)

    return {
        "name": "Extracted Groove",
        "category": "User",
        "grid_beats": grid_beats,
        "steps": steps,
        "timing": timing,
        "velocity": velocity,
        "length": length,
    }


# ---------------------------------------------------------------------------
# Apply Groove to Notes
# ---------------------------------------------------------------------------

def apply_groove_to_notes(notes: List[Any], groove: Dict[str, Any],
                          amount: float = 1.0,
                          affect_timing: bool = True,
                          affect_velocity: bool = True,
                          affect_length: bool = False) -> List[Any]:
    """Apply a groove template to a list of MIDI notes.

    Args:
        notes: List of MidiNote-like objects (must have .clone())
        groove: Groove template dict
        amount: Groove intensity 0.0 (none) to 1.0 (full), can exceed 1.0
        affect_timing: Apply timing offsets
        affect_velocity: Apply velocity multipliers
        affect_length: Apply length multipliers

    Returns:
        New list of modified notes (originals are NOT mutated)
    """
    if not groove or amount <= 0.0:
        return list(notes)

    grid_beats = float(groove.get("grid_beats", 0.25))
    steps = int(groove.get("steps", 16))
    g_timing = groove.get("timing", [])
    g_velocity = groove.get("velocity", [])
    g_length = groove.get("length", [])
    amount = float(_clamp(amount, 0.0, 2.0))

    result = []
    for n in notes:
        try:
            nn = n.clone()
            start = float(getattr(nn, 'start_beats', 0.0))

            # Find nearest grid position
            grid_pos = round(start / grid_beats) if grid_beats > 0.001 else 0
            step_idx = int(grid_pos) % steps

            # Timing offset
            if affect_timing and step_idx < len(g_timing):
                offset = float(g_timing[step_idx]) * amount
                nn.start_beats = max(0.0, start + offset)

            # Velocity multiplier
            if affect_velocity and step_idx < len(g_velocity):
                vel_mult = 1.0 + (float(g_velocity[step_idx]) - 1.0) * amount
                new_vel = int(round(float(getattr(nn, 'velocity', 100)) * vel_mult))
                nn.velocity = max(1, min(127, new_vel))

            # Length multiplier
            if affect_length and step_idx < len(g_length):
                len_mult = 1.0 + (float(g_length[step_idx]) - 1.0) * amount
                new_len = float(getattr(nn, 'length_beats', 0.125)) * len_mult
                nn.length_beats = max(0.03125, new_len)

            result.append(nn)
        except Exception:
            result.append(n)  # keep original on error

    return result


# ---------------------------------------------------------------------------
# Humanize
# ---------------------------------------------------------------------------

def humanize_notes(notes: List[Any],
                   timing_range: float = 0.02,
                   velocity_range: int = 15,
                   length_range: float = 0.1,
                   amount: float = 1.0,
                   seed: Optional[int] = None) -> List[Any]:
    """Apply random humanization to MIDI notes.

    Args:
        notes: List of MidiNote-like objects (must have .clone())
        timing_range: Max timing offset in beats (default ±0.02 = ~10ms at 120 BPM)
        velocity_range: Max velocity variation (default ±15)
        length_range: Max length variation as fraction (default ±10%)
        amount: Humanization intensity (0.0 to 1.0)
        seed: Random seed for reproducibility (None = random)

    Returns:
        New list of humanized notes
    """
    if amount <= 0.0:
        return list(notes)

    rng = random.Random(seed)
    amount = float(_clamp(amount, 0.0, 1.0))
    timing_range = float(timing_range) * amount
    velocity_range = int(round(float(velocity_range) * amount))
    length_range = float(length_range) * amount

    result = []
    for n in notes:
        try:
            nn = n.clone()

            # Timing humanization (gaussian distribution for natural feel)
            if timing_range > 0.0:
                t_off = rng.gauss(0.0, timing_range * 0.5)
                t_off = _clamp(t_off, -timing_range, timing_range)
                nn.start_beats = max(0.0, float(nn.start_beats) + t_off)

            # Velocity humanization
            if velocity_range > 0:
                v_off = int(round(rng.gauss(0.0, velocity_range * 0.5)))
                v_off = max(-velocity_range, min(velocity_range, v_off))
                nn.velocity = max(1, min(127, int(nn.velocity) + v_off))

            # Length humanization
            if length_range > 0.0:
                l_factor = 1.0 + rng.gauss(0.0, length_range * 0.5)
                l_factor = _clamp(l_factor, 1.0 - length_range, 1.0 + length_range)
                nn.length_beats = max(0.03125, float(nn.length_beats) * l_factor)

            result.append(nn)
        except Exception:
            result.append(n)

    return result
