"""Scale database + constraint helpers.

We use the shared JSON from ``pydaw/notation/scales/scales.json`` (already part of the project)
and expose small helpers:

- ``allowed_pitch_classes(...)`` -> list[int] (0..11)
- ``apply_scale_constraint(pitch, allowed, mode)`` -> int | None

Modes:
    - ``snap``: out-of-scale pitches are moved to nearest allowed pitch
    - ``reject``: out-of-scale pitches are rejected (return None)
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional


_NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def pc_name(pc: int) -> str:
    return _NOTE_NAMES[int(pc) % 12]


@lru_cache(maxsize=1)
def _load_scales_json() -> dict:
    # Keep a single source-of-truth: the notation scales file.
    base = Path(__file__).resolve().parents[1]
    p = base / "notation" / "scales" / "scales.json"
    if not p.exists():
        # fallback: allow future relocation without breaking
        p = base / "data" / "scales" / "scales.json"
    return json.loads(p.read_text(encoding="utf-8"))


def list_scale_categories() -> list[str]:
    d = _load_scales_json()
    return list(d.keys())


def list_scales_in_category(category: str) -> list[str]:
    d = _load_scales_json()
    cat = d.get(str(category), {}) if isinstance(d, dict) else {}
    if not isinstance(cat, dict):
        return []
    return list(cat.keys())


def allowed_pitch_classes(
    *,
    category: str,
    name: str,
    root_pc: int,
) -> list[int]:
    """Return allowed pitch classes (0..11) for the selected scale.

    The JSON stores intervals in *cents* (100 cents == one semitone in 12-TET).
    For our MIDI constraint we convert to semitone steps.
    """

    d = _load_scales_json()
    cat = d.get(str(category), {}) if isinstance(d, dict) else {}
    entry = cat.get(str(name), {}) if isinstance(cat, dict) else {}
    cents = entry.get("intervals_cent", []) if isinstance(entry, dict) else []

    out: set[int] = set()
    rp = int(root_pc) % 12

    # Special case: "Keine Einschränkung" -> allow all.
    if str(category) == "Keine Einschränkung":
        return list(range(12))

    for c in cents:
        try:
            semis = int(round(float(c) / 100.0))
        except Exception:
            continue
        out.add((rp + semis) % 12)
    if not out:
        # safe fallback
        return list(range(12))
    return sorted(out)


def is_pitch_allowed(pitch: int, allowed_pcs: Iterable[int]) -> bool:
    try:
        pcs = set(int(x) % 12 for x in allowed_pcs)
    except Exception:
        pcs = set()
    if not pcs:
        return True
    return (int(pitch) % 12) in pcs


def nearest_allowed_pitch(pitch: int, allowed_pcs: Iterable[int]) -> int:
    """Snap pitch to nearest pitch whose pitch-class is in allowed_pcs."""

    p = int(pitch)
    pcs = set(int(x) % 12 for x in allowed_pcs)
    if not pcs:
        return p
    if (p % 12) in pcs:
        return p

    # Search outward by semitone distance.
    for dist in range(1, 12):
        up = p + dist
        dn = p - dist
        if (up % 12) in pcs:
            return up
        if (dn % 12) in pcs:
            return dn
    return p


def apply_scale_constraint(pitch: int, allowed_pcs: Optional[Iterable[int]], mode: str) -> Optional[int]:
    """Apply constraint.

    Returns:
        - int: pitch to use
        - None: reject the note (only in 'reject' mode)
    """

    if allowed_pcs is None:
        return int(pitch)

    m = str(mode or "snap").lower().strip()
    if m == "reject":
        return int(pitch) if is_pitch_allowed(int(pitch), allowed_pcs) else None
    # default: snap
    return int(nearest_allowed_pitch(int(pitch), allowed_pcs))
