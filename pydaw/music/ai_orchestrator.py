"""AI Orchestrator (multi-track MIDI generator).

Goal:
    Create multiple *instrument* tracks + MIDI clips in one operation.

Design constraints:
    - No heavy ML deps; pure python + deterministic seed
    - Reuse the existing AI-Composer musical heuristics
    - Produce stable, readable parts (track-per-instrument)

This module is intentionally additive and does not change existing engine code.

v0.0.20.195: initial orchestrator engine.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Dict, Iterable, List, Tuple

from pydaw.model.midi import MidiNote
from pydaw.music.ai_composer import ComposerParams, beats_per_bar, generate_clip_notes


# -------------------------------
# Ensemble templates
# -------------------------------


@dataclass(frozen=True)
class PartSpec:
    name: str
    role: str  # "lead" | "harmony" | "bass" | "counter" | "chords" | "arp" | "perc"
    low: int
    high: int
    octave_shift: int = 0
    density_mul: float = 1.0


ENSEMBLES: Dict[str, Tuple[PartSpec, ...]] = {
    # Small, flexible template — user assigns instruments later (SF2/Sampler/etc.)
    "Kammermusik": (
        PartSpec("Violine I", "lead", 67, 96, 0, 1.00),
        PartSpec("Violine II", "counter", 60, 90, 0, 0.90),
        PartSpec("Viola", "harmony", 55, 84, 0, 0.85),
        PartSpec("Cello", "bass", 36, 67, 0, 0.95),
        PartSpec("Kontrabass", "bass", 28, 55, -12, 0.55),
        PartSpec("Harfe", "arp", 48, 96, 0, 0.70),
    ),
    "Hofmusik": (
        PartSpec("Flöte", "lead", 72, 103, 12, 0.75),
        PartSpec("Violine", "lead", 67, 96, 0, 0.85),
        PartSpec("Viola", "harmony", 55, 84, 0, 0.70),
        PartSpec("Cello", "bass", 36, 67, 0, 0.85),
        PartSpec("Cembalo", "arp", 48, 96, 0, 0.90),
    ),
    "Schlossmusik": (
        PartSpec("Violine I", "lead", 67, 96, 0, 0.90),
        PartSpec("Violine II", "counter", 60, 90, 0, 0.80),
        PartSpec("Viola", "harmony", 55, 84, 0, 0.75),
        PartSpec("Cello", "bass", 36, 67, 0, 0.90),
        PartSpec("Harfe", "arp", 48, 96, 0, 0.65),
        PartSpec("Horn", "chords", 48, 79, 0, 0.55),
    ),
    "Gottesdienst/Kirche": (
        PartSpec("Orgel", "chords", 36, 96, 0, 0.95),
        PartSpec("Chor (Sopran)", "lead", 69, 96, 0, 0.70),
        PartSpec("Chor (Alt)", "harmony", 60, 84, 0, 0.65),
        PartSpec("Chor (Tenor)", "harmony", 55, 79, -12, 0.60),
        PartSpec("Chor (Bass)", "bass", 36, 67, 0, 0.75),
        PartSpec("Streicher", "counter", 55, 96, 0, 0.45),
    ),
    "Volles Orchester": (
        # Strings
        PartSpec("Violine I", "lead", 67, 96, 0, 0.95),
        PartSpec("Violine II", "counter", 60, 90, 0, 0.85),
        PartSpec("Viola", "harmony", 55, 84, 0, 0.80),
        PartSpec("Cello", "bass", 36, 67, 0, 0.90),
        PartSpec("Kontrabass", "bass", 28, 55, -12, 0.55),
        # Woodwinds
        PartSpec("Flöte", "lead", 72, 103, 12, 0.55),
        PartSpec("Oboe", "lead", 67, 96, 0, 0.45),
        PartSpec("Klarinette", "harmony", 55, 91, 0, 0.45),
        PartSpec("Fagott", "bass", 36, 72, 0, 0.35),
        # Brass
        PartSpec("Hörner", "chords", 43, 79, 0, 0.45),
        PartSpec("Trompeten", "lead", 60, 96, 0, 0.35),
        PartSpec("Posaunen", "chords", 40, 72, 0, 0.30),
        PartSpec("Tuba", "bass", 28, 55, 0, 0.25),
        # Extras
        PartSpec("Harfe", "arp", 48, 96, 0, 0.55),
        PartSpec("Timpani", "perc", 35, 55, 0, 0.25),
    ),
}


# -------------------------------
# Helpers
# -------------------------------


def _fit_pitch_to_range(p: int, low: int, high: int) -> int:
    p = int(p)
    low = int(low)
    high = int(high)
    # Shift by octaves into range.
    while p < low:
        p += 12
    while p > high:
        p -= 12
    return max(0, min(127, int(p)))


def _pick_mode(params: ComposerParams) -> str:
    g = (params.genre_b or params.genre_a or "").lower()
    ctx = (params.context or "").lower()
    if "gottes" in ctx or "kirch" in ctx or "gospel" in g:
        return "major"
    if "metal" in g or "hardcore" in g or "industrial" in g:
        return "minor"
    if "techno" in g or "house" in g or "trance" in g:
        return "minor"
    return "major"


def _group_by_start(notes: Iterable[MidiNote], grid: float) -> Dict[float, List[MidiNote]]:
    g = max(0.0625, float(grid))
    out: Dict[float, List[MidiNote]] = {}
    for n in notes:
        try:
            k = round(float(n.start_beats) / g) * g
            out.setdefault(float(k), []).append(n)
        except Exception:
            continue
    return out


def _split_roles(base_notes: List[MidiNote], grid: float) -> Tuple[List[MidiNote], List[MidiNote], List[MidiNote]]:
    """Return (bass, lead, harmony/counter)."""
    bass = [n for n in base_notes if int(n.pitch) < 60]

    grouped = _group_by_start([n for n in base_notes if int(n.pitch) >= 60], grid)
    lead: List[MidiNote] = []
    rest: List[MidiNote] = []
    for _, lst in grouped.items():
        if not lst:
            continue
        # choose the highest pitch as lead at that onset
        top = max(lst, key=lambda x: int(x.pitch))
        lead.append(top)
        for n in lst:
            if n is top:
                continue
            rest.append(n)

    # fallback: if lead is empty, use mid notes
    if not lead:
        mid = [n for n in base_notes if 60 <= int(n.pitch) <= 84]
        lead = mid[:]

    lead.sort(key=lambda x: (float(x.start_beats), -int(x.pitch)))
    bass.sort(key=lambda x: (float(x.start_beats), int(x.pitch)))
    rest.sort(key=lambda x: (float(x.start_beats), int(x.pitch)))
    return bass, lead, rest


def _make_chords(
    *,
    bass_notes: List[MidiNote],
    bpb: float,
    bars: int,
    mode: str,
    grid: float,
    density: float,
) -> List[MidiNote]:
    """Simple block chords on bar starts, derived from bass."""
    third = 3 if mode == "minor" else 4
    fifth = 7
    out: List[MidiNote] = []
    # pick one bass per bar
    by_bar: Dict[int, MidiNote] = {}
    for n in bass_notes:
        bi = int(float(n.start_beats) // float(bpb))
        if bi not in by_bar:
            by_bar[bi] = n
    for bi in range(max(1, int(bars))):
        root_n = by_bar.get(bi)
        if not root_n:
            continue
        if random.random() > (0.35 + 0.55 * float(density)):
            continue
        t0 = float(bi) * float(bpb)
        root = int(root_n.pitch)
        dur = max(float(grid) * 4.0, float(bpb) * (0.75 if density > 0.5 else 1.0))
        vel = int(55 + 30 * float(density))
        for interval in (0, third, fifth):
            out.append(MidiNote(pitch=root + interval + 12, start_beats=t0, length_beats=dur, velocity=vel).clamp())
    out.sort(key=lambda x: (float(x.start_beats), int(x.pitch)))
    return out


def _make_arps(
    *,
    chords: List[MidiNote],
    grid: float,
    density: float,
) -> List[MidiNote]:
    """Arpeggiate chords (harp/cembalo)."""
    step = max(0.0625, float(grid))
    out: List[MidiNote] = []
    # group chord tones by bar start
    by_start: Dict[float, List[MidiNote]] = {}
    for n in chords:
        by_start.setdefault(float(n.start_beats), []).append(n)

    for t0, tones in by_start.items():
        if not tones:
            continue
        tones = sorted(tones, key=lambda x: int(x.pitch))
        # 8 steps per bar-ish at 1/8 by default
        steps = int(max(4, min(16, round(4.0 / step))))
        for i in range(steps):
            if random.random() > (0.40 + 0.60 * float(density)):
                continue
            sel = tones[i % len(tones)]
            out.append(
                MidiNote(
                    pitch=int(sel.pitch),
                    start_beats=float(t0) + float(i) * step,
                    length_beats=max(step * 0.85, step),
                    velocity=max(35, int(sel.velocity) - 10),
                ).clamp()
            )
    out.sort(key=lambda x: (float(x.start_beats), int(x.pitch)))
    return out


def _make_timpani(
    *,
    bass_notes: List[MidiNote],
    bpb: float,
    bars: int,
    density: float,
) -> List[MidiNote]:
    out: List[MidiNote] = []
    by_bar: Dict[int, MidiNote] = {}
    for n in bass_notes:
        bi = int(float(n.start_beats) // float(bpb))
        if bi not in by_bar:
            by_bar[bi] = n
    for bi in range(max(1, int(bars))):
        if random.random() > (0.20 + 0.30 * float(density)):
            continue
        bn = by_bar.get(bi)
        if not bn:
            continue
        p = int(bn.pitch)
        out.append(MidiNote(pitch=p, start_beats=float(bi) * float(bpb), length_beats=float(bpb) * 0.5, velocity=80).clamp())
    return out


def _apply_part_transform(
    source: List[MidiNote],
    *,
    spec: PartSpec,
    seed: int,
    base_density: float,
    context: str,
) -> List[MidiNote]:
    """Copy notes into the part range + thin by density."""
    rnd = random.Random(int(seed) & 0x7FFFFFFF)
    # stable per-part variation
    rnd.seed((int(seed) & 0x7FFFFFFF) ^ (hash(spec.name) & 0x7FFFFFFF))

    density = max(0.0, min(1.0, float(base_density) * float(spec.density_mul)))
    ctx = (context or "").lower()
    stacc = ("club" in ctx) or ("industrie" in ctx)
    legato = ("gottes" in ctx) or ("kirch" in ctx)

    out: List[MidiNote] = []
    for n in source:
        if rnd.random() > (0.20 + 0.80 * density):
            continue
        p = int(n.pitch) + int(spec.octave_shift)
        p = _fit_pitch_to_range(p, spec.low, spec.high)
        dur = float(n.length_beats)
        if stacc:
            dur = max(0.125, dur * 0.55)
        if legato:
            dur = max(0.25, dur * 1.15)
        vel = int(n.velocity)
        if spec.role in ("bass", "perc"):
            vel = min(127, max(45, vel + 8))
        out.append(
            MidiNote(
                pitch=p,
                start_beats=float(n.start_beats),
                length_beats=float(dur),
                velocity=int(vel),
            ).clamp()
        )

    out.sort(key=lambda x: (float(x.start_beats), int(x.pitch)))
    return out


# -------------------------------
# Public API
# -------------------------------


def available_ensembles() -> Tuple[str, ...]:
    return tuple(ENSEMBLES.keys())


def build_parts(
    *,
    time_signature: str,
    params: ComposerParams,
    ensemble: str,
    selected_parts: Iterable[str] | None = None,
) -> Dict[str, List[MidiNote]]:
    """Generate multi-track parts (notes are relative to clip start = 0.0)."""
    ensemble_key = str(ensemble or "Kammermusik")
    specs = ENSEMBLES.get(ensemble_key) or ENSEMBLES["Kammermusik"]
    selected = set(str(x) for x in (selected_parts or []))
    if selected:
        specs = tuple(s for s in specs if s.name in selected)

    # deterministic seed
    seed = int(getattr(params, "seed", 1) or 1)
    random.seed(seed & 0x7FFFFFFF)

    # base clip notes (3 voices)
    base = generate_clip_notes(start_beats=0.0, time_signature=str(time_signature or "4/4"), params=params)

    grid = max(0.0625, float(getattr(params, "grid", 0.25) or 0.25))
    density = max(0.0, min(1.0, float(getattr(params, "density", 0.65) or 0.65)))
    bars = max(1, int(getattr(params, "bars", 8) or 8))
    bpb = beats_per_bar(str(time_signature or "4/4"))

    bass, lead, rest = _split_roles(list(base), grid)
    mode = _pick_mode(params)

    chords = _make_chords(bass_notes=bass, bpb=bpb, bars=bars, mode=mode, grid=grid, density=density)
    arps = _make_arps(chords=chords, grid=grid, density=density)
    timp = _make_timpani(bass_notes=bass, bpb=bpb, bars=bars, density=density)

    # role sources
    sources: Dict[str, List[MidiNote]] = {
        "bass": bass,
        "lead": lead,
        "counter": rest if rest else lead,
        "harmony": rest if rest else lead,
        "chords": chords,
        "arp": arps,
        "perc": timp,
    }

    parts: Dict[str, List[MidiNote]] = {}
    for spec in specs:
        src = sources.get(spec.role, lead)
        parts[spec.name] = _apply_part_transform(
            list(src),
            spec=spec,
            seed=seed,
            base_density=density,
            context=str(getattr(params, "context", "Neutral") or "Neutral"),
        )

    return parts
