"""AI-driven (algorithmic) drum pattern generator.

This module mirrors the philosophy of :mod:`pydaw.music.ai_composer`:

- No static MIDI files
- Deterministic with a seed (reproducible)
- Lightweight, pure Python (safe for GUI usage)

Design goal for the Pro Drum Machine:

*Keep the canonical drum note mapping stable* (C2 Kick, C#2 Snare, ...)
so PianoRoll and Notation stay readable.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Dict, List, Tuple

from pydaw.model.midi import MidiNote


def beats_per_bar(time_signature: str) -> float:
    try:
        num_s, den_s = str(time_signature or "4/4").split("/", 1)
        num = max(1, int(num_s.strip()))
        den = max(1, int(den_s.strip()))
        return float(num) * (4.0 / float(den))
    except Exception:
        return 4.0


def _clamp01(x: float) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except Exception:
        return 0.5


GRID_TO_STEPS: Dict[str, int] = {
    "1/8": 8,
    "1/16": 16,
    "1/32": 32,
}


@dataclass(frozen=True)
class DrumParams:
    genre_a: str = "Electro"
    genre_b: str = "Hardcore"
    hybrid: float = 0.35
    context: str = "Neutral"
    bars: int = 1
    grid: str = "1/16"
    swing: float = 0.0
    density: float = 0.65
    intensity: float = 0.55
    seed: str = "Random"  # "Random" or numeric string


ROLE_TO_SLOT_INDEX: Dict[str, int] = {
    "kick": 0,
    "snare": 1,
    "chat": 2,
    "ohat": 3,
    "clap": 4,
    "tom": 5,
    "perc": 6,
    "rim": 7,
    "fx1": 8,
    "fx2": 9,
    "ride": 10,
    "crash": 11,
}


def _seed_to_int(seed: str) -> int:
    s = str(seed or "Random").strip()
    if not s or s.lower() == "random":
        return random.randint(0, 2**31 - 1)
    try:
        return int(s)
    except Exception:
        # stable hash-ish fallback
        acc = 0
        for ch in s:
            acc = (acc * 131 + ord(ch)) & 0x7FFFFFFF
        return int(acc)


def _idx_for_time(t_beats: float, beats_bar: float, steps: int) -> int:
    # snap to grid
    x = float(t_beats) / max(0.0001, float(beats_bar))
    i = int(round(x * float(steps)))
    return max(0, min(int(steps) - 1, i))


def _empty_probs(steps: int) -> List[float]:
    return [0.0 for _ in range(int(steps))]


def _add_hits(probs: List[float], *, times: List[float], p: float, beats_bar: float) -> None:
    steps = len(probs)
    for t in times:
        i = _idx_for_time(float(t), beats_bar, steps)
        probs[i] = max(float(probs[i]), float(p))


def _hat_times(subdivision: float) -> List[float]:
    # subdivision in beats (0.5 => 8th notes)
    times = []
    t = 0.0
    while t < 4.0 - 1e-9:
        times.append(t)
        t += float(subdivision)
    return times


def _genre_profile(genre: str, steps: int, beats_bar: float) -> Dict[str, List[float]]:
    """Return per-role probability arrays (0..1) for one bar."""
    g = (genre or "").lower()
    beats_bar = float(beats_bar or 4.0)

    kick = _empty_probs(steps)
    snare = _empty_probs(steps)
    clap = _empty_probs(steps)
    chat = _empty_probs(steps)
    ohat = _empty_probs(steps)
    tom = _empty_probs(steps)
    perc = _empty_probs(steps)
    ride = _empty_probs(steps)
    crash = _empty_probs(steps)
    rim = _empty_probs(steps)

    # Common anchors in beats (assuming 4/4-ish)
    backbeats = [1.0, 3.0]
    downbeats = [0.0, 1.0, 2.0, 3.0]

    # Default: pop/rock-ish
    _add_hits(kick, times=[0.0, 2.0], p=0.85, beats_bar=beats_bar)
    _add_hits(snare, times=backbeats, p=0.90, beats_bar=beats_bar)
    _add_hits(chat, times=_hat_times(0.5), p=0.70, beats_bar=beats_bar)

    if "house" in g or "techno" in g or "electro" in g or "trance" in g:
        _add_hits(kick, times=downbeats, p=0.98, beats_bar=beats_bar)  # four-on-the-floor
        _add_hits(clap, times=backbeats, p=0.70, beats_bar=beats_bar)
        _add_hits(snare, times=backbeats, p=0.55, beats_bar=beats_bar)
        _add_hits(chat, times=_hat_times(0.5), p=0.85, beats_bar=beats_bar)
        _add_hits(ohat, times=[0.5, 1.5, 2.5, 3.5], p=0.65, beats_bar=beats_bar)
        _add_hits(crash, times=[0.0], p=0.35, beats_bar=beats_bar)

    if "hip" in g or "r&b" in g or "soul" in g or "trap" in g:
        # syncopated kicks + backbeat
        kick2 = [0.0, 0.75, 2.25, 2.75]
        _add_hits(kick, times=kick2, p=0.75, beats_bar=beats_bar)
        _add_hits(snare, times=backbeats, p=0.92, beats_bar=beats_bar)
        _add_hits(chat, times=_hat_times(0.25), p=0.55, beats_bar=beats_bar)  # 16ths
        _add_hits(rim, times=[1.75, 3.75], p=0.30, beats_bar=beats_bar)

    if "dnb" in g or "drum" in g and "bass" in g or "jungle" in g:
        # two-step-ish
        _add_hits(kick, times=[0.0, 2.5], p=0.90, beats_bar=beats_bar)
        _add_hits(snare, times=[1.5, 3.5], p=0.95, beats_bar=beats_bar)
        _add_hits(chat, times=_hat_times(0.25), p=0.65, beats_bar=beats_bar)
        _add_hits(ohat, times=[0.75, 2.75], p=0.55, beats_bar=beats_bar)

    if "hardcore" in g or "gabba" in g or "speedcore" in g:
        # relentless
        _add_hits(kick, times=_hat_times(0.25), p=0.90, beats_bar=beats_bar)  # 16th kicks
        _add_hits(snare, times=backbeats, p=0.55, beats_bar=beats_bar)
        _add_hits(clap, times=backbeats, p=0.45, beats_bar=beats_bar)
        _add_hits(chat, times=_hat_times(0.25), p=0.85, beats_bar=beats_bar)
        _add_hits(crash, times=[0.0], p=0.25, beats_bar=beats_bar)

    if "punk" in g or "rock" in g:
        _add_hits(kick, times=[0.0, 2.0, 2.5], p=0.80, beats_bar=beats_bar)
        _add_hits(snare, times=backbeats, p=0.98, beats_bar=beats_bar)
        _add_hits(chat, times=_hat_times(0.5), p=0.90, beats_bar=beats_bar)
        _add_hits(crash, times=[0.0], p=0.30, beats_bar=beats_bar)

    if "metal" in g:
        # double-kick tendency
        _add_hits(kick, times=_hat_times(0.25), p=0.70, beats_bar=beats_bar)
        _add_hits(snare, times=backbeats, p=0.92, beats_bar=beats_bar)
        _add_hits(ride, times=_hat_times(0.5), p=0.55, beats_bar=beats_bar)
        _add_hits(crash, times=[0.0, 2.0], p=0.40, beats_bar=beats_bar)
        _add_hits(tom, times=[3.5, 3.75], p=0.25, beats_bar=beats_bar)

    if "gottesdienst" in g or "kirche" in g or "kirchenmusik" in g:
        # sparse + gentle
        _add_hits(kick, times=[0.0], p=0.55, beats_bar=beats_bar)
        _add_hits(snare, times=[2.0], p=0.55, beats_bar=beats_bar)
        _add_hits(chat, times=_hat_times(1.0), p=0.35, beats_bar=beats_bar)

    if "country" in g or "folk" in g:
        _add_hits(kick, times=[0.0, 2.0], p=0.65, beats_bar=beats_bar)
        _add_hits(snare, times=backbeats, p=0.80, beats_bar=beats_bar)
        _add_hits(ride, times=_hat_times(1.0), p=0.40, beats_bar=beats_bar)

    return {
        "kick": kick,
        "snare": snare,
        "clap": clap,
        "chat": chat,
        "ohat": ohat,
        "tom": tom,
        "perc": perc,
        "ride": ride,
        "crash": crash,
        "rim": rim,
    }


def _mix_profiles(a: Dict[str, List[float]], b: Dict[str, List[float]], h: float) -> Dict[str, List[float]]:
    h = _clamp01(h)
    out: Dict[str, List[float]] = {}
    roles = set(a.keys()) | set(b.keys())
    for r in roles:
        pa = a.get(r) or []
        pb = b.get(r) or []
        n = max(len(pa), len(pb))
        if n <= 0:
            out[r] = []
            continue
        if len(pa) != n:
            pa = (pa + [0.0] * n)[:n]
        if len(pb) != n:
            pb = (pb + [0.0] * n)[:n]
        out[r] = [(1.0 - h) * float(pa[i]) + h * float(pb[i]) for i in range(n)]
    return out


def _context_mods(context: str) -> Tuple[float, float, float]:
    """Return (density_mul, intensity_mul, fill_mul)."""
    c = (context or "").lower()
    if "gottesdienst" in c:
        return 0.70, 0.70, 0.40
    if "hof" in c or "schloss" in c or "kammer" in c:
        return 0.85, 0.85, 0.65
    if "club" in c:
        return 1.10, 1.05, 1.00
    if "stadion" in c:
        return 1.05, 1.10, 1.10
    if "industrie" in c or "industrial" in c:
        return 1.10, 1.15, 1.15
    if "keller" in c:
        return 0.95, 0.95, 0.85
    return 1.0, 1.0, 1.0


def generate_drum_notes(*, params: DrumParams, base_note: int, time_signature: str = "4/4") -> List[MidiNote]:
    """Generate MIDI notes for a drum clip.

    Args:
        params: generation parameters
        base_note: C2 base note (36) for Slot1
        time_signature: currently optimized for 4/4; other TS are handled by scaling.
    """

    beats_bar = beats_per_bar(time_signature)
    steps = int(GRID_TO_STEPS.get(str(params.grid), 16))
    step_beats = float(beats_bar) / float(steps)

    rng = random.Random(_seed_to_int(params.seed))

    a = _genre_profile(params.genre_a, steps, beats_bar)
    b = _genre_profile(params.genre_b, steps, beats_bar)
    prof = _mix_profiles(a, b, params.hybrid)

    density = _clamp01(params.density)
    intensity = _clamp01(params.intensity)
    swing = _clamp01(params.swing)

    d_mul, i_mul, fill_mul = _context_mods(params.context)
    density *= d_mul
    intensity *= i_mul

    # Per-role velocity bases
    vel_base = {
        "kick": 104,
        "snare": 98,
        "clap": 86,
        "chat": 58,
        "ohat": 66,
        "ride": 64,
        "crash": 86,
        "tom": 78,
        "perc": 70,
        "rim": 64,
    }

    # Probability scalers per role
    p_scale = {
        "kick": 0.60 + 0.80 * intensity,
        "snare": 0.55 + 0.70 * intensity,
        "clap": 0.45 + 0.70 * intensity,
        "chat": 0.30 + 1.00 * density,
        "ohat": 0.20 + 0.90 * density,
        "ride": 0.25 + 0.80 * density,
        "crash": 0.15 + 0.70 * intensity,
        "tom": 0.10 + 0.60 * intensity,
        "perc": 0.10 + 0.65 * density,
        "rim": 0.10 + 0.55 * density,
    }

    notes: List[MidiNote] = []
    seen = set()

    bars = max(1, int(params.bars))
    for bar in range(bars):
        bar_off = float(bar) * float(beats_bar)

        # Fill window in last bar
        is_last = (bar == bars - 1)

        for s in range(steps):
            t = bar_off + float(s) * step_beats

            # Swing: push odd steps a bit late (works best on 1/16 and finer)
            if steps >= 16 and (s % 2) == 1 and swing > 0.0:
                t += swing * (step_beats * 0.33)

            for role, probs in prof.items():
                if not probs:
                    continue
                p = float(probs[s])
                if p <= 0.0:
                    continue

                p *= float(p_scale.get(role, 1.0))

                # Reduce crashes/hats in very sparse contexts
                if role in ("crash", "ohat") and density < 0.25:
                    p *= 0.6

                if rng.random() > min(1.0, max(0.0, p)):
                    continue

                slot_idx = ROLE_TO_SLOT_INDEX.get(role)
                if slot_idx is None:
                    continue
                pitch = int(base_note) + int(slot_idx)

                # Accent: downbeats louder
                base_v = int(vel_base.get(role, 80))
                acc = 1.0
                if s == 0:
                    acc = 1.15
                if role == "kick" and (s % max(1, (steps // 4))) == 0:
                    acc = max(acc, 1.10)
                if role in ("snare", "clap") and (abs((t - bar_off) - 1.0) < 0.01 or abs((t - bar_off) - 3.0) < 0.01):
                    acc = max(acc, 1.08)

                v = int(base_v * (0.70 + 0.60 * intensity) * acc)
                v = max(1, min(127, v))

                key = (pitch, round(t, 6))
                if key in seen:
                    continue
                seen.add(key)
                notes.append(MidiNote(pitch=pitch, start_beats=float(t), length_beats=max(0.125, step_beats), velocity=v).clamp())

            # Simple end-of-phrase fill
            if is_last and fill_mul > 0.0:
                # last 1/2 beat: occasional tom/perc
                if (beats_bar - (t - bar_off)) <= 0.5 + 1e-6:
                    if rng.random() < (0.12 * fill_mul) * (0.35 + intensity):
                        pitch = int(base_note) + int(ROLE_TO_SLOT_INDEX["tom"]) 
                        notes.append(MidiNote(pitch=pitch, start_beats=float(t), length_beats=max(0.125, step_beats), velocity=int(70 + 40 * intensity)).clamp())
                    if rng.random() < (0.10 * fill_mul) * (0.35 + density):
                        pitch = int(base_note) + int(ROLE_TO_SLOT_INDEX["perc"]) 
                        notes.append(MidiNote(pitch=pitch, start_beats=float(t), length_beats=max(0.125, step_beats), velocity=int(60 + 35 * intensity)).clamp())

        # Constraint: ensure at least a kick at bar start
        if not any((n.pitch == int(base_note) + ROLE_TO_SLOT_INDEX["kick"] and abs(n.start_beats - bar_off) < 0.001) for n in notes):
            notes.append(MidiNote(pitch=int(base_note) + ROLE_TO_SLOT_INDEX["kick"], start_beats=bar_off, length_beats=max(0.125, step_beats), velocity=int(100 + 20 * intensity)).clamp())

        # Constraint: ensure at least a backbeat snare in 4/4-like bars
        if beats_bar >= 4.0 - 1e-6:
            for bb in (bar_off + 1.0, bar_off + 3.0):
                if not any((n.pitch == int(base_note) + ROLE_TO_SLOT_INDEX["snare"] and abs(n.start_beats - bb) < 0.02) for n in notes):
                    notes.append(MidiNote(pitch=int(base_note) + ROLE_TO_SLOT_INDEX["snare"], start_beats=float(bb), length_beats=max(0.125, step_beats), velocity=int(90 + 25 * intensity)).clamp())

    # Sort by time then pitch (stable)
    notes.sort(key=lambda n: (float(n.start_beats), int(n.pitch)))
    return notes
