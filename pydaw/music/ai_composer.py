"""AI-driven (algorithmic) MIDI composition helpers.

This is intentionally *not* a static MIDI library.

We generate sequences on demand using lightweight mathematical / stochastic
algorithms. The goal is an MVP that is:

- deterministic with a seed (reproducible)
- fast (pure Python)
- safe for GUI usage (no heavy ML dependencies)

v0.0.20.191: initial engine for the "AI Composer" Note-FX.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Iterable, List, Tuple

from pydaw.model.midi import MidiNote


# A broad but finite list. The UI also provides "Custom" for any missing ones.
GENRES: Tuple[str, ...] = (
    "Barock (Bach/Fuge)",
    "Klassik",
    "Romantik",
    "Filmmusik",
    "Ambient",
    "Downtempo",
    "Lo-Fi",
    "Hip-Hop",
    "Trap",
    "R&B",
    "Soul",
    "Funk",
    "Disco",
    "House",
    "Techno",
    "Electro",
    "Electro-Punk",
    "Industrial",
    "EBM",
    "Hardcore",
    "Drum & Bass",
    "Jungle",
    "Dubstep",
    "Trance",
    "Synthwave",
    "Chiptune",
    "Rock",
    "Punk",
    "Metal",
    "Trash Metal",
    "Death Metal",
    "Black Metal",
    "Prog Metal",
    "Jazz",
    "Bebop",
    "Bossa Nova",
    "Reggae",
    "Ska",
    "Latin",
    "Flamenco",
    "Folk",
    "World",
    "Gospel",
    "Kirchenmusik",
)


CONTEXTS: Tuple[str, ...] = (
    "Neutral",
    "Gottesdienst",
    "Hofmusik",
    "Schlossmusik",
    "Kammermusik",
    "Industriehalle",
    "Club",
    "Stadion",
    "Keller-Session",
)


FORMS: Tuple[str, ...] = (
    "Motiv/Sequenz",
    "2-stimmiger Kontrapunkt",
    "Mini-Fuge (Subject/Answer)",
    "Riff + Hook",
    "Pad/Drone + Melodie",
)


INSTRUMENT_SETUPS: Tuple[str, ...] = (
    "Bass",
    "Violine",
    "Kammermusik-Setup",
    "Industrial-Setup",
    "Volles Orchester",
)


def beats_per_bar(time_signature: str) -> float:
    try:
        num_s, den_s = str(time_signature or "4/4").split("/", 1)
        num = max(1, int(num_s.strip()))
        den = max(1, int(den_s.strip()))
        return float(num) * (4.0 / float(den))
    except Exception:
        return 4.0


def _quantize(x: float, step: float) -> float:
    if step <= 0:
        return float(x)
    return round(float(x) / float(step)) * float(step)


def _clamp01(x: float) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except Exception:
        return 0.5


_MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)
_MINOR_SCALE = (0, 2, 3, 5, 7, 8, 10)


def _scale_for_genre(genre: str) -> Tuple[Tuple[int, ...], int]:
    g = (genre or "").lower()
    # crude but effective heuristics
    if "barock" in g or "kirche" in g or "gospel" in g:
        return _MAJOR_SCALE, 0
    if "metal" in g or "hardcore" in g or "industrial" in g:
        return _MINOR_SCALE, 0
    if "r&b" in g or "soul" in g or "jazz" in g:
        return _MINOR_SCALE, 0
    if "techno" in g or "house" in g or "trance" in g:
        return _MINOR_SCALE, 0
    return _MAJOR_SCALE, 0


def _rhythm_pattern(genre: str, *, grid: float, swing: float, density: float) -> List[float]:
    """Return a list of onset offsets (within a bar) in beats."""
    g = (genre or "").lower()
    density = _clamp01(density)
    swing = _clamp01(swing)

    # base step length in beats
    step = max(grid, 0.0625)
    # build a bar as 4 beats (pattern generator is later scaled per TS)
    max_steps = int(round(4.0 / step))
    onsets = []

    def _maybe_add(i: int, prob: float) -> None:
        if random.random() <= prob:
            t = float(i) * step
            # apply swing to off-steps (odd indices)
            if (i % 2) == 1:
                t += swing * (step * 0.33)
            onsets.append(t)

    if "hardcore" in g or "dnb" in g or "jungle" in g:
        # dense 1/16-ish with accents
        for i in range(max_steps):
            _maybe_add(i, 0.45 + 0.45 * density)
    elif "trash" in g or "metal" in g:
        # palm-mute style: bursts
        for i in range(max_steps):
            base = 0.15 + 0.55 * density
            if (i % 4) == 0:
                base += 0.25
            _maybe_add(i, base)
    elif "r&b" in g or "soul" in g or "funk" in g:
        # syncopated
        for i in range(max_steps):
            base = 0.10 + 0.35 * density
            if i in (0, 3, 7, 10, 12, 15):
                base += 0.35
            _maybe_add(i, base)
    elif "electro" in g or "techno" in g or "house" in g or "industrial" in g:
        # four-on-the-floor-ish
        for i in range(max_steps):
            base = 0.05 + 0.30 * density
            if (i % int(round(1.0 / step))) == 0:
                base += 0.55
            _maybe_add(i, base)
    elif "barock" in g or "klassik" in g or "romantik" in g:
        # flowing
        for i in range(max_steps):
            _maybe_add(i, 0.25 + 0.55 * density)
    else:
        for i in range(max_steps):
            _maybe_add(i, 0.20 + 0.45 * density)

    onsets = sorted(set(_quantize(t, step) for t in onsets))
    return [t for t in onsets if 0.0 <= t < 4.0]


def _choose_progression(bars: int, mode: str) -> List[int]:
    """Return chord degrees (0..6) for each bar."""
    # Small palettes that sound okay in many genres.
    if mode == "minor":
        pool = [0, 5, 3, 6]  # i - VI - iv - VII (approx)
    else:
        pool = [0, 4, 5, 3]  # I - V - VI - IV
    prog = []
    for i in range(max(1, int(bars))):
        prog.append(pool[i % len(pool)])
    return prog


def _degree_to_pitch(root: int, scale: Tuple[int, ...], degree: int, octave: int) -> int:
    degree = int(degree) % 7
    pc = int(scale[degree])
    return int(root + pc + 12 * int(octave))


def _walk_melody(
    *,
    root: int,
    scale: Tuple[int, ...],
    chord_degree: int,
    start_pitch: int,
    steps: int,
    max_leap: int,
) -> List[int]:
    """Random walk constrained to scale + prefers chord tones."""
    pitches: List[int] = []
    p = int(start_pitch)

    chord_tones = {
        _degree_to_pitch(root, scale, chord_degree, 0) % 12,
        _degree_to_pitch(root, scale, (chord_degree + 2) % 7, 0) % 12,
        _degree_to_pitch(root, scale, (chord_degree + 4) % 7, 0) % 12,
    }

    # Precompute allowed pitch classes
    allowed_pc = {int(x) % 12 for x in scale}

    for _ in range(max(1, int(steps))):
        # move by small intervals
        leap = random.randint(-max_leap, max_leap)
        if leap == 0:
            leap = random.choice([-2, -1, 1, 2])
        cand = p + leap
        # snap to scale pc
        for _try in range(12):
            if (cand % 12) in allowed_pc:
                break
            cand += 1 if leap > 0 else -1
        # chord-tone attraction
        if (cand % 12) not in chord_tones and random.random() < 0.35:
            # pull towards nearest chord tone
            best = cand
            best_d = 999
            for ct in chord_tones:
                # choose ct near cand
                for k in (-24, -12, 0, 12, 24):
                    c2 = (cand // 12) * 12 + ct + k
                    d = abs(c2 - cand)
                    if d < best_d:
                        best, best_d = c2, d
            cand = best

        p = int(max(36, min(96, cand)))
        pitches.append(p)

    return pitches


@dataclass
class ComposerParams:
    genre_a: str = "Barock (Bach/Fuge)"
    genre_b: str = "Electro"
    custom_genre_a: str = ""
    custom_genre_b: str = ""
    context: str = "Neutral"
    form: str = "Mini-Fuge (Subject/Answer)"
    instrument_setup: str = "Kammermusik-Setup"
    bars: int = 8
    grid: float = 0.25  # 1/16 in beats (quarter note beat)
    swing: float = 0.0
    density: float = 0.65
    hybrid: float = 0.55
    seed: int = 1


def generate_clip_notes(
    *,
    start_beats: float,
    time_signature: str,
    params: ComposerParams,
    base_root: int = 60,
) -> List[MidiNote]:
    """Generate a list of MidiNote for a new clip.

    The engine produces a compact 2-3 voice texture:
    - Bass voice (root-ish)
    - Lead voice (melody)
    - Optional counter voice for baroque forms
    """

    # Seeded randomness (reproducible)
    random.seed(int(params.seed) & 0x7FFFFFFF)

    # resolve custom genre strings
    ga = params.custom_genre_a.strip() if (params.genre_a == "Custom" and params.custom_genre_a) else params.genre_a
    gb = params.custom_genre_b.strip() if (params.genre_b == "Custom" and params.custom_genre_b) else params.genre_b

    scale_a, _ = _scale_for_genre(ga)
    scale_b, _ = _scale_for_genre(gb)
    hybrid = _clamp01(params.hybrid)

    # hybridize scale choice
    scale = scale_a if random.random() > hybrid else scale_b
    mode = "minor" if scale == _MINOR_SCALE else "major"

    # context nudges
    root = int(base_root)
    ctx = (params.context or "").lower()
    if "gottes" in ctx or "kirch" in ctx:
        mode = "major"
        root = 60
    if "industrie" in ctx or "club" in ctx:
        root = 57
        mode = "minor"

    # grid in beats
    grid = max(0.0625, float(params.grid))
    swing = _clamp01(params.swing)
    density = _clamp01(params.density)

    bpb = beats_per_bar(time_signature)
    bars = max(1, int(params.bars))
    total_beats = float(bars) * float(bpb)

    # progression (per bar)
    prog = _choose_progression(bars, mode)

    # rhythm: mix genre A/B
    pat_a = _rhythm_pattern(ga, grid=grid, swing=swing, density=density)
    pat_b = _rhythm_pattern(gb, grid=grid, swing=swing, density=density)
    pat = pat_a if random.random() > hybrid else pat_b

    # stretch pattern to TS bars
    # (pattern is for 4 beats; scale if bar length != 4)
    scale_bar = float(bpb) / 4.0
    pat = [t * scale_bar for t in pat]

    notes: List[MidiNote] = []

    # ---- bass voice
    for bi in range(bars):
        deg = prog[bi % len(prog)]
        t0 = float(start_beats) + float(bi) * bpb
        # downbeat + occasional pickup
        bass_pitch = _degree_to_pitch(root, scale, deg, -2)
        vel = 92 if ("metal" in (gb or "").lower() or "hardcore" in (gb or "").lower()) else 76
        notes.append(MidiNote(pitch=bass_pitch, start_beats=t0, length_beats=max(grid * 2.0, bpb * 0.5), velocity=vel).clamp())
        if density > 0.55 and random.random() < 0.5:
            notes.append(MidiNote(pitch=bass_pitch, start_beats=t0 + (bpb * 0.75), length_beats=max(grid, bpb * 0.25), velocity=max(45, vel - 18)).clamp())

    # ---- lead voice
    # start in mid register
    lead_pitch = _degree_to_pitch(root, scale, prog[0], 0) + 12
    for bi in range(bars):
        deg = prog[bi % len(prog)]
        tbar = float(start_beats) + float(bi) * bpb
        onsets = list(pat)
        random.shuffle(onsets)
        onsets = sorted(onsets[: max(2, int(len(pat) * (0.35 + 0.55 * density)))])
        mel = _walk_melody(
            root=root,
            scale=scale,
            chord_degree=deg,
            start_pitch=lead_pitch,
            steps=len(onsets),
            max_leap=3 if ("barock" in (ga or "").lower()) else 5,
        )
        lead_pitch = mel[-1] if mel else lead_pitch
        for i, off in enumerate(onsets):
            st = tbar + float(off)
            if st >= (start_beats + total_beats):
                continue
            dur = grid * (2.0 if random.random() < 0.4 else 1.0)
            vel = int(75 + 35 * density)
            if "r&b" in (gb or "").lower():
                vel = int(60 + 30 * density)
            notes.append(MidiNote(pitch=int(mel[i]), start_beats=_quantize(st, grid), length_beats=max(grid, dur), velocity=vel).clamp())

    # ---- optional counter voice
    form = (params.form or "").lower()
    if "kontrapunkt" in form or "fuge" in form:
        # simple inversion / answer at fifth
        counter_shift = 7 if "fuge" in form else 0
        for n in list(notes):
            # only mirror lead notes (mid/high register)
            if int(n.pitch) < 60:
                continue
            if random.random() > (0.45 + 0.45 * density):
                continue
            cp = int(n.pitch)
            # invert around root+12
            pivot = int(root + 12)
            inv = pivot - (cp - pivot) + counter_shift
            inv = max(48, min(96, inv))
            notes.append(MidiNote(pitch=inv, start_beats=float(n.start_beats) + grid * (1.0 if random.random() < 0.5 else 0.0), length_beats=max(grid, float(n.length_beats) * 0.9), velocity=max(40, int(n.velocity) - 18)).clamp())

    # final clamp + sort
    out = [nn.clamp() for nn in notes]
    out.sort(key=lambda x: (float(x.start_beats), int(x.pitch)))
    return out
