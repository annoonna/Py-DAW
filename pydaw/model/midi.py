"""MIDI domain helpers.

We keep MIDI note data in a clip-scoped structure.

Notes are primarily represented as simple rectangles for the Piano Roll.
For upcoming notation support we also store a minimal "spelling" (accidental)
and a tie flag. These fields are optional, backward compatible, and do *not*
change existing playback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class MidiNote:
    pitch: int        # 0..127
    start_beats: float
    length_beats: float
    velocity: int = 100
    # Notation helpers (optional)
    accidental: int = 0      # -2=bb, -1=b, 0=natural/none, 1=#, 2=##
    tie_to_next: bool = False

    # v0.0.20.196: Note Expressions (MPE-style, per-note)
    #
    # JSON-safe structure:
    #   expressions[param] = [ {"t": 0.0..1.0, "v": float}, ... ]
    #
    # - t is note-local normalized time (0=start of note, 1=end of note)
    # - v is parameter value (normalized 0..1 for most params; semitones for micropitch)
    #
    # NOTE: We intentionally keep this JSON-native (dict/list/float) so
    # projects stay forward/backward compatible and we don't force a heavy
    # model migration.
    expressions: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    # v0.0.20.199: Curve types per segment (optional)
    #   expression_curve_types[param] = ["linear"|"smooth", ...]  # length = max(0, n_points-1)
    # Used for rendering and segment behavior in the Expression Lane.
    expression_curve_types: Dict[str, List[str]] = field(default_factory=dict)

    def clamp(self) -> "MidiNote":
        self.pitch = max(0, min(127, int(self.pitch)))
        self.length_beats = max(0.125, float(self.length_beats))
        self.start_beats = max(0.0, float(self.start_beats))
        self.velocity = max(1, min(127, int(self.velocity)))
        self.accidental = max(-2, min(2, int(getattr(self, "accidental", 0))))
        self.tie_to_next = bool(getattr(self, "tie_to_next", False))

        # Clamp note expressions (best-effort, backward/forward compatible)
        try:
            expr = getattr(self, "expressions", None)
            if not isinstance(expr, dict):
                self.expressions = {}
            else:
                fixed: Dict[str, List[Dict[str, Any]]] = {}
                for k, pts in expr.items():
                    if not k:
                        continue
                    if not isinstance(pts, list):
                        continue
                    out: List[Dict[str, Any]] = []
                    for p in pts:
                        if not isinstance(p, dict):
                            continue
                        try:
                            t = float(p.get("t", 0.0))
                            v = float(p.get("v", 0.0))
                        except Exception:
                            continue
                        t = max(0.0, min(1.0, t))
                        out.append({"t": t, "v": v})
                    if out:
                        out.sort(key=lambda d: float(d.get("t", 0.0)))
                        fixed[str(k)] = out
                self.expressions = fixed

                # Clamp curve types (best-effort)
                try:
                    ct = getattr(self, 'expression_curve_types', None)
                    if not isinstance(ct, dict):
                        self.expression_curve_types = {}
                    else:
                        fixed_ct: Dict[str, List[str]] = {}
                        for k2, segs in ct.items():
                            if not k2 or not isinstance(segs, list):
                                continue
                            out2: List[str] = []
                            for s in segs:
                                ss = str(s).strip().lower()
                                if ss not in ('linear', 'smooth'):
                                    continue
                                out2.append(ss)
                            if out2:
                                fixed_ct[str(k2)] = out2
                        self.expression_curve_types = fixed_ct
                except Exception:
                    self.expression_curve_types = {}
        except Exception:
            self.expressions = {}
        return self

    # ----------------- Note Expression helpers -----------------

    def get_expression_points(self, param: str) -> List[Dict[str, Any]]:
        """Return sorted expression points for *param* (JSON-safe dicts)."""
        pts = (getattr(self, "expressions", {}) or {}).get(str(param), [])
        if not isinstance(pts, list):
            return []
        out = [p for p in pts if isinstance(p, dict)]
        try:
            out.sort(key=lambda d: float(d.get("t", 0.0)))
        except Exception:
            pass
        return out

    def set_expression_points(self, param: str, points: List[Dict[str, Any]] | None) -> None:
        """Set expression points for *param*.

        Points are normalized note-local time dicts: {"t":0..1, "v":float}.
        """
        if not isinstance(getattr(self, "expressions", None), dict):
            self.expressions = {}
        p = str(param)
        if not points:
            try:
                self.expressions.pop(p, None)
            except Exception:
                pass
            return
        out: List[Dict[str, Any]] = []
        for d in points:
            if not isinstance(d, dict):
                continue
            try:
                t = max(0.0, min(1.0, float(d.get("t", 0.0))))
                v = float(d.get("v", 0.0))
            except Exception:
                continue
            out.append({"t": t, "v": v})
        out.sort(key=lambda dd: float(dd.get("t", 0.0)))
        self.expressions[p] = out

    
    def get_expression_curve_types(self, param: str, n_points: int | None = None) -> List[str]:
        """Return curve types for segments of *param*.

        The list length is (n_points-1). Values: 'linear' or 'smooth'.
        If missing or mismatched, returns best-effort defaults.
        """
        p = str(param)
        ct = getattr(self, "expression_curve_types", {}) or {}
        segs = ct.get(p, [])
        if not isinstance(segs, list):
            segs = []
        out = [str(s).strip().lower() for s in segs if str(s).strip().lower() in ("linear", "smooth")]
        if n_points is None:
            try:
                n_points = len(self.get_expression_points(p))
            except Exception:
                n_points = 0
        try:
            n_seg = max(0, int(n_points) - 1)
        except Exception:
            n_seg = 0
        # Default by param (micropitch tends to want smooth)
        default = "smooth" if p == "micropitch" else "linear"
        if len(out) < n_seg:
            out = out + [default] * (n_seg - len(out))
        if len(out) > n_seg:
            out = out[:n_seg]
        return out

    def set_expression_curve_types(self, param: str, seg_types: List[str] | None) -> None:
        """Set curve types for *param* segments."""
        if not isinstance(getattr(self, "expression_curve_types", None), dict):
            self.expression_curve_types = {}
        p = str(param)
        if not seg_types:
            try:
                self.expression_curve_types.pop(p, None)
            except Exception:
                pass
            return
        out: List[str] = []
        for s in seg_types:
            ss = str(s).strip().lower()
            if ss in ("linear", "smooth"):
                out.append(ss)
        if out:
            self.expression_curve_types[p] = out
        else:
            try:
                self.expression_curve_types.pop(p, None)
            except Exception:
                pass

    def scale_expression_time(self, param: str, scale: float) -> None:
            """Scale expression curve time inside the note (Bitwig-style morph base).
    
            This scales normalized time in-place: t' = clamp(t * scale).
            """
            try:
                s = float(scale)
            except Exception:
                return
            if s <= 0.0:
                return
            pts = self.get_expression_points(str(param))
            if not pts:
                return
            out: List[Dict[str, Any]] = []
            for d in pts:
                try:
                    t = max(0.0, min(1.0, float(d.get("t", 0.0)) * s))
                    v = float(d.get("v", 0.0))
                except Exception:
                    continue
                out.append({"t": t, "v": v})
            out.sort(key=lambda dd: float(dd.get("t", 0.0)))
            if not isinstance(getattr(self, "expressions", None), dict):
                self.expressions = {}
            self.expressions[str(param)] = out
    
    # ----------------- Notation conversion -----------------
    #
    # Staff position model (minimal, stable):
    #   - line: diatonic step within octave (C=0..B=6)
    #   - octave: scientific octave number where C4 == MIDI 60
    #
    # This is NOT a full engraving model; it is just enough to map a MIDI pitch
    # to a predictable staff position for WIP notation rendering.

    _PC_TO_LINE_ACC = {
        0: (0, 0),   # C
        1: (0, 1),   # C#
        2: (1, 0),   # D
        3: (1, 1),   # D#
        4: (2, 0),   # E
        5: (3, 0),   # F
        6: (3, 1),   # F#
        7: (4, 0),   # G
        8: (4, 1),   # G#
        9: (5, 0),   # A
        10: (5, 1),  # A#
        11: (6, 0),  # B
    }

    _LINE_TO_NATURAL_PC = {
        0: 0,   # C
        1: 2,   # D
        2: 4,   # E
        3: 5,   # F
        4: 7,   # G
        5: 9,   # A
        6: 11,  # B
    }

    def to_staff_position(self) -> Tuple[int, int]:
        """Convert this MIDI note's pitch to a minimal staff position.

        Returns:
            (line, octave) where line is 0..6 (C..B) and octave follows the
            scientific convention (C4 == MIDI 60).

        Side effect:
            Updates ``self.accidental`` to match the derived pitch spelling.
        """

        p = int(self.pitch)
        p = max(0, min(127, p))
        octave = (p // 12) - 1
        pc = p % 12

        line, acc = self._PC_TO_LINE_ACC.get(pc, (0, 0))
        self.accidental = int(acc)
        return int(line), int(octave)

    @staticmethod
    def from_staff_position(line: int, octave: int, accidental: int = 0) -> int:
        """Convert a staff position back to a MIDI pitch.

        Args:
            line: diatonic step in octave (C=0..B=6)
            octave: scientific octave number where C4 == MIDI 60
            accidental: optional chromatic alteration (-2..2)

        Returns:
            MIDI pitch (0..127)
        """

        if int(line) not in MidiNote._LINE_TO_NATURAL_PC:
            raise ValueError(f"Invalid staff line index: {line} (expected 0..6)")

        natural_pc = MidiNote._LINE_TO_NATURAL_PC[int(line)]
        acc = max(-2, min(2, int(accidental)))
        pitch = (int(octave) + 1) * 12 + int(natural_pc) + acc
        return max(0, min(127, int(pitch)))


MidiClipNotes = Dict[str, List[MidiNote]]
