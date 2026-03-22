"""Note Expression evaluation helpers (playback-side).

Goal (safe):
- Provide deterministic, lightweight evaluation of per-note expression data stored in
  MidiNote.expressions (JSON-safe dict).
- Keep this module free of UI dependencies.

We intentionally start with "note-on" usage only:
- Velocity: sampled at t=0.0 (note start)
- Chance: sampled at t=0.0 (note start)
- Timbre (CC74): sampled at t=0.0 (note start)
- Pressure (poly aftertouch): sampled at t=0.0 (note start)

Micropitch helpers are handled conservatively here.\nFor realtime-safe playback we expose a note-start helper; continuous per-note\ncurve playback can be layered on top by callers (e.g. SF2 offline render).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import hashlib


def _clamp01(x: float) -> float:
    try:
        v = float(x)
    except Exception:
        return 0.0
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def get_expr_points(note: Any, param: str) -> List[Dict[str, Any]]:
    """Return sorted expression points for *param*.

    Supports:
    - MidiNote objects (attribute: expressions)
    - dict notes (key: "expressions")

    Points are dicts: {"t":0..1, "v":float}
    """
    p = str(param)
    expr = None
    if isinstance(note, dict):
        expr = note.get("expressions")
    else:
        expr = getattr(note, "expressions", None)

    if not isinstance(expr, dict):
        return []

    pts = expr.get(p, [])
    if not isinstance(pts, list):
        return []

    out = [d for d in pts if isinstance(d, dict)]
    try:
        out.sort(key=lambda d: float(d.get("t", 0.0)))
    except Exception:
        pass
    return out


def eval_points_linear(points: List[Dict[str, Any]], t: float) -> Optional[float]:
    """Evaluate points at normalized time *t* using linear interpolation.

    Returns None if points empty.
    """
    if not points:
        return None
    try:
        tt = float(t)
    except Exception:
        tt = 0.0
    if tt <= float(points[0].get("t", 0.0)):
        try:
            return float(points[0].get("v", 0.0))
        except Exception:
            return 0.0
    if tt >= float(points[-1].get("t", 1.0)):
        try:
            return float(points[-1].get("v", 0.0))
        except Exception:
            return 0.0

    # Find segment (small lists; linear scan is fine and safe)
    prev = points[0]
    for nxt in points[1:]:
        try:
            t0 = float(prev.get("t", 0.0))
            t1 = float(nxt.get("t", 0.0))
        except Exception:
            prev = nxt
            continue
        if t1 <= t0:
            prev = nxt
            continue
        if tt <= t1:
            try:
                v0 = float(prev.get("v", 0.0))
                v1 = float(nxt.get("v", 0.0))
            except Exception:
                return 0.0
            a = (tt - t0) / (t1 - t0)
            return (1.0 - a) * v0 + a * v1
        prev = nxt

    try:
        return float(points[-1].get("v", 0.0))
    except Exception:
        return 0.0


def eval_expr(note: Any, param: str, t: float = 0.0) -> Optional[float]:
    pts = get_expr_points(note, param)
    return eval_points_linear(pts, t)


def effective_velocity(note: Any) -> int:
    """Return MIDI velocity (1..127) for note-on.

    If a velocity expression exists, it overrides the base note.velocity.
    Otherwise returns note.velocity.
    """
    v_expr = eval_expr(note, "velocity", 0.0)
    if v_expr is None:
        try:
            return max(1, min(127, int(getattr(note, "velocity", 100) if not isinstance(note, dict) else note.get("velocity", 100))))
        except Exception:
            return 100
    # expression value is normalized 0..1
    vv = _clamp01(v_expr)
    vel = int(round(vv * 127.0))
    return max(1, min(127, vel))


def effective_chance(note: Any) -> float:
    """Return chance probability 0..1.

    If no chance expression exists: returns 1.0
    """
    c_expr = eval_expr(note, "chance", 0.0)
    if c_expr is None:
        return 1.0
    return _clamp01(c_expr)


def should_play_note(*, clip_id: str, note: Any, abs_start_beats: float) -> bool:
    """Deterministic chance gate.

    - If chance is 1.0 -> always play.
    - Else compute a deterministic pseudo-random value based on clip_id, pitch, time.

    This avoids "random" bouncing during re-renders and makes projects stable.
    """
    chance = effective_chance(note)
    if chance >= 1.0:
        return True
    if chance <= 0.0:
        return False

    try:
        pitch = int(getattr(note, "pitch", 60) if not isinstance(note, dict) else note.get("pitch", 60))
    except Exception:
        pitch = 60

    # Deterministic random in [0,1)
    h = hashlib.sha1(f"{clip_id}|{abs_start_beats:.6f}|{pitch}|chance".encode("utf-8")).digest()
    r = int.from_bytes(h[:4], "big") / float(2**32)
    return r <= chance




def effective_micropitch(note: Any, t: float = 0.0) -> Optional[float]:
    """Return note-local micropitch in semitones.

    Stored values are already semitone offsets (typically -12..+12).
    Returns None if no micropitch expression exists.
    """
    v = eval_expr(note, "micropitch", t)
    if v is None:
        return None
    try:
        vv = float(v)
    except Exception:
        return None
    return max(-12.0, min(12.0, vv))


def effective_micropitch_note_start(note: Any) -> Optional[float]:
    """Return a robust note-start micropitch value in semitones.

    Safe rationale:
    - Pure t=0.0 can sound like "no difference" when the first visible bend
      starts a few pixels after note start.
    - We therefore average a tiny early window (0..10% of the note), which is
      still musically close to the attack but audibly more reliable.
    """
    pts = get_expr_points(note, "micropitch")
    if not pts:
        return None
    vals = []
    for tt, w in ((0.0, 0.5), (0.05, 0.3), (0.10, 0.2)):
        v = eval_points_linear(pts, tt)
        if v is None:
            continue
        try:
            vals.append((float(v), float(w)))
        except Exception:
            pass
    if not vals:
        return effective_micropitch(note, 0.0)
    num = sum(v * w for v, w in vals)
    den = max(1e-9, sum(w for _v, w in vals))
    try:
        vv = float(num / den)
    except Exception:
        return None
    return max(-12.0, min(12.0, vv))


def micropitch_curve_points(note: Any, steps: int = 12) -> List[tuple[float, float]]:
    """Return lightweight sampled micropitch curve points [(t, semitones), ...].

    Used for safe offline MPE-ish rendering (e.g. FluidSynth pitchwheel).
    Returns an empty list when no usable curve exists.
    """
    pts = get_expr_points(note, "micropitch")
    if len(pts) < 2:
        return []
    try:
        n = max(2, min(64, int(steps)))
    except Exception:
        n = 12
    out: List[tuple[float, float]] = []
    last_v: Optional[float] = None
    for i in range(n + 1):
        tt = float(i) / float(n)
        v = eval_points_linear(pts, tt)
        if v is None:
            continue
        try:
            vv = max(-12.0, min(12.0, float(v)))
        except Exception:
            continue
        if last_v is None or abs(vv - float(last_v)) >= 0.03 or i in (0, n):
            out.append((tt, vv))
            last_v = vv
    return out


def cc74_value(note: Any) -> Optional[int]:
    """Return CC74 value 0..127 if timbre expression exists."""
    v = eval_expr(note, "timbre", 0.0)
    if v is None:
        return None
    return max(0, min(127, int(round(_clamp01(v) * 127.0))))


def pressure_value(note: Any) -> Optional[int]:
    """Return pressure value 0..127 if pressure expression exists."""
    v = eval_expr(note, "pressure", 0.0)
    if v is None:
        return None
    return max(0, min(127, int(round(_clamp01(v) * 127.0))))
