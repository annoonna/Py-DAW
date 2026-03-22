# -*- coding: utf-8 -*-
"""Note-FX Chain (MIDI vor Instrument).

Engine-first MVP:
- JSON-safe chain spec lives in Track.note_fx_chain
- prepare_clips() applies Note-FX to MIDI notes before:
  - SF2 pre-render
  - MIDI event stream for Sampler/Drum plugins
- UI uses the same helpers for preview routing.

Spec (Track.note_fx_chain):
{
  "devices": [
     {"plugin_id":"chrono.note_fx.transpose","id":"nfx_xxx","enabled":true,"params":{"semitones":0}},
     ...
  ]
}
"""
from __future__ import annotations

import json
import hashlib
import random
from dataclasses import replace
from typing import Any, Iterable, List, Tuple


def _clamp_midi(v: int) -> int:
    return max(0, min(127, int(v)))

def _clamp(v: float, lo: float, hi: float) -> float:
    try:
        return max(float(lo), min(float(hi), float(v)))
    except Exception:
        return float(lo)

# --- Note-FX helpers (MVP set)

_SCALE_PATTERNS = {
    "major":       [0, 2, 4, 5, 7, 9, 11],
    "minor":       [0, 2, 3, 5, 7, 8, 10],
    "dorian":      [0, 2, 3, 5, 7, 9, 10],
    "phrygian":    [0, 1, 3, 5, 7, 8, 10],
    "lydian":      [0, 2, 4, 6, 7, 9, 11],
    "mixolydian":  [0, 2, 4, 5, 7, 9, 10],
    "locrian":     [0, 1, 3, 5, 6, 8, 10],
    "pentatonic":  [0, 2, 4, 7, 9],
    "chromatic":   list(range(12)),
}

_CHORD_INTERVALS = {
    "maj":   [0, 4, 7],
    "min":   [0, 3, 7],
    "power": [0, 7],
    "maj7":  [0, 4, 7, 11],
    "min7":  [0, 3, 7, 10],
    "dom7":  [0, 4, 7, 10],
    "dim":   [0, 3, 6],
    "dim7":  [0, 3, 6, 9],
    "aug":   [0, 4, 8],
    "sus2":  [0, 2, 7],
    "sus4":  [0, 5, 7],
    "add9":  [0, 4, 7, 14],
    "min9":  [0, 3, 7, 10, 14],
    "maj9":  [0, 4, 7, 11, 14],
    "6":     [0, 4, 7, 9],
    "min6":  [0, 3, 7, 9],
}

def _stable_seed_int(s: str) -> int:
    d = hashlib.md5(s.encode("utf-8")).digest()
    return int.from_bytes(d[:8], "little", signed=False)

def _snap_pitch_to_scale(pitch: int, root: int, scale: str, mode: str = "nearest") -> int:
    pitch = int(_clamp_midi(pitch))
    root = int(root) % 12
    patt = _SCALE_PATTERNS.get(str(scale or "major"), _SCALE_PATTERNS["major"])
    allowed_pcs = { (root + int(x)) % 12 for x in patt }

    # generate candidates around pitch (±12 semitones)
    candidates = []
    for oct_shift in (-12, 0, 12):
        base = pitch + oct_shift
        base_oct = (base // 12) * 12
        for pc in allowed_pcs:
            cand = base_oct + pc
            if 0 <= cand <= 127:
                candidates.append(cand)
    if not candidates:
        return pitch

    if mode == "down":
        cands = [c for c in candidates if c <= pitch]
        return max(cands) if cands else min(candidates)
    if mode == "up":
        cands = [c for c in candidates if c >= pitch]
        return min(cands) if cands else max(candidates)

    # nearest
    candidates.sort(key=lambda c: (abs(c - pitch), c))
    return int(candidates[0])


def note_fx_chain_signature(chain: Any) -> str:
    """Stable signature string used for cache keys.

    If the chain changes, rendered SF2 WAV cache must be invalidated.
    """
    try:
        return json.dumps(chain or {}, sort_keys=True, ensure_ascii=False)
    except Exception:
        try:
            return str(chain)
        except Exception:
            return ""


def apply_note_fx_chain_to_pitch_velocity(pitch: int, velocity: int, chain: Any) -> List[Tuple[int, int]]:
    """Apply Note-FX chain to a single (pitch, velocity) pair.

    Returns a list because future Note-FX (arp/chord) can expand events.
    """
    out: List[Tuple[int, int]] = [(_clamp_midi(pitch), _clamp_midi(velocity))]
    devices = []
    if isinstance(chain, dict):
        devices = chain.get("devices", []) or []
    elif isinstance(chain, list):
        devices = chain
    for dev in devices:
        if not isinstance(dev, dict):
            continue
        if dev.get("enabled", True) is False:
            continue
        pid = (dev.get("plugin_id") or dev.get("type") or "").strip()
        params = dev.get("params", {}) if isinstance(dev.get("params", {}), dict) else {}
        if pid in ("chrono.note_fx.transpose", "transpose", "TransposeFx"):
            semis = int(params.get("semitones", 0) or 0)
            out = [(_clamp_midi(p + semis), v) for (p, v) in out]
        elif pid in ("chrono.note_fx.velocity_scale", "velocity_scale", "VelocityScaleFx"):
            scale = float(params.get("scale", 1.0) or 1.0)
            out = [(p, _clamp_midi(int(round(v * scale)))) for (p, v) in out]
        else:
            # Unknown device: ignore (forward compatible)
            continue
    return out


def apply_note_fx_chain_to_notes(notes: Iterable[Any], chain: Any) -> List[Any]:
    """
    Applies Note-FX devices to a list of note-like objects (expects .clone(), .pitch, .velocity, .start_beats, .length_beats).
    Supported (MVP): Transpose, VelScale, ScaleSnap, Chord, Random, Arp.
    """
    try:
        devices = []
        if isinstance(chain, dict):
            devices = chain.get("devices", []) or []
        if not devices:
            return list(notes)

        out_notes: List[Any] = list(notes)

        def _apply_arp(in_notes: List[Any], params: dict, dev_id: str) -> List[Any]:
            step = float(params.get("step_beats", 0.5) or 0.5)
            mode = str(params.get("mode", "up") or "up").strip().lower()
            octaves = int(params.get("octaves", 1) or 1)
            gate = float(params.get("gate", 0.9) or 0.9)
            note_type = str(params.get("note_type", "straight") or "straight").strip().lower()
            shuffle_enabled = bool(params.get("shuffle_enabled", False))
            shuffle_steps = int(params.get("shuffle_steps", 16) or 16)
            step_data = params.get("step_data", []) if isinstance(params.get("step_data", []), list) else []
            seed_base = int(params.get("seed", 0) or 0)

            step = float(max(0.0625, min(4.0, step)))
            octaves = int(max(1, min(4, octaves)))
            gate = float(max(0.1, min(4.0, gate)))
            shuffle_steps = int(max(1, min(16, shuffle_steps)))
            if note_type in ("dotted", "punktiert"):
                step *= 1.5
            elif note_type in ("triplets", "triplet", "triolen"):
                step *= (2.0 / 3.0)

            def _expand_seq(pitches_sorted: list[int]) -> list[int]:
                seq: list[int] = []
                for o in range(octaves):
                    for p in pitches_sorted:
                        pp = int(p) + 12 * o
                        if 0 <= pp <= 127:
                            seq.append(pp)
                return seq or list(pitches_sorted)

            def _interleave_low_high(seq: list[int], start_high: bool = False) -> list[int]:
                if not seq:
                    return []
                lo = 0
                hi = len(seq) - 1
                out: list[int] = []
                high_turn = bool(start_high)
                while lo <= hi:
                    if high_turn:
                        out.append(seq[hi])
                        hi -= 1
                    else:
                        out.append(seq[lo])
                        lo += 1
                    high_turn = not high_turn
                return out

            def _blossom(seq: list[int], reverse: bool = False) -> list[int]:
                if not seq:
                    return []
                if reverse:
                    seq = list(reversed(seq))
                n = len(seq)
                left = (n - 1) // 2
                right = left + 1
                out = [seq[left]]
                while left - 1 >= 0 or right < n:
                    if right < n:
                        out.append(seq[right])
                        right += 1
                    if left - 1 >= 0:
                        left -= 1
                        out.append(seq[left])
                return out

            def _flow(seq: list[int], rnd: random.Random) -> list[int]:
                if not seq:
                    return []
                if len(seq) <= 2:
                    return list(seq)
                pos = rnd.randint(0, len(seq) - 1)
                direction = 1 if rnd.random() < 0.5 else -1
                out = [seq[pos]]
                for _ in range(max(3, len(seq) * 3)):
                    pos += direction
                    if pos <= 0:
                        pos = 0
                        direction = 1
                    elif pos >= len(seq) - 1:
                        pos = len(seq) - 1
                        direction = -1
                    if rnd.random() < 0.18:
                        direction *= -1
                    out.append(seq[pos])
                return out

            def _seq_for_mode(seq: list[int], mode_name: str, rnd: random.Random) -> tuple[str, object]:
                norm = mode_name.replace("/", " ").replace("+", " + ").replace("&", " & ")
                norm = " ".join(norm.split())
                compact = norm.replace(" ", "")
                if not seq:
                    return ("note", [])
                if compact in ("up",):
                    return ("note", list(seq))
                if compact in ("down",):
                    return ("note", list(reversed(seq)))
                if compact in ("updown", "up/down", "up/down2", "up/down3"):
                    base = list(seq)
                    if len(base) > 1:
                        return ("note", base + list(reversed(base[1:-1])))
                    return ("note", base)
                if compact in ("random",):
                    base = list(seq)
                    rnd.shuffle(base)
                    return ("note", base)
                if compact in ("chords", "chord"):
                    return ("chord", list(seq))
                if compact in ("flow",):
                    return ("note", _flow(list(seq), rnd))
                if compact in ("up+in", "upin"):
                    return ("note", _interleave_low_high(list(seq), start_high=False))
                if compact in ("down+in", "downin"):
                    return ("note", _interleave_low_high(list(reversed(seq)), start_high=False))
                if compact in ("blossomup",):
                    return ("note", _blossom(list(seq), reverse=False))
                if compact in ("blossomdown",):
                    return ("note", _blossom(list(seq), reverse=True))
                if compact in ("low&up", "lowup"):
                    return ("note", _interleave_low_high(list(seq), start_high=False))
                if compact in ("low&down", "lowdown"):
                    return ("note", _interleave_low_high(list(reversed(seq)), start_high=False))
                if compact in ("hi&up", "hiup"):
                    return ("note", _interleave_low_high(list(seq), start_high=True))
                if compact in ("hi&down", "hidown"):
                    return ("note", _interleave_low_high(list(reversed(seq)), start_high=True))
                return ("note", list(seq))

            result: List[Any] = []
            groups = {}
            for n in in_notes:
                try:
                    key = round(float(getattr(n, "start_beats", 0.0)), 6)
                except Exception:
                    key = 0.0
                groups.setdefault(key, []).append(n)

            for key in sorted(groups.keys()):
                g = groups[key]
                if not g:
                    continue
                pitches = [int(getattr(n, "pitch", 60) or 60) for n in g]
                velocities = [int(getattr(n, "velocity", 100) or 100) for n in g]
                base_vel = int(_clamp(max(velocities) if velocities else 100, 1, 127))
                pitches_sorted = sorted(set(pitches))
                seq = _expand_seq(pitches_sorted)
                seed = seed_base or _stable_seed_int(f"{dev_id}|{key}|{len(seq)}")
                rnd = random.Random(int(seed) ^ _stable_seed_int(f"{dev_id}|{key}|{mode}"))
                event_kind, event_payload = _seq_for_mode(seq, mode, rnd)
                if not event_payload:
                    event_kind, event_payload = ("note", list(seq or pitches_sorted))

                try:
                    group_end = max(float(getattr(n, "start_beats", 0.0)) + float(getattr(n, "length_beats", 0.125)) for n in g)
                except Exception:
                    group_end = float(key) + 0.5
                group_start = float(key)
                total_len = max(0.125, group_end - group_start)
                count = max(1, int(total_len / step + 1e-9))
                template = g[0].clone()

                for i in range(count):
                    step_idx = i % 16
                    step_cfg = step_data[step_idx] if step_idx < len(step_data) and isinstance(step_data[step_idx], dict) else {}
                    if bool(step_cfg.get("skip", False)):
                        continue
                    transpose = int(step_cfg.get("transpose", 0) or 0)
                    vel_step = int(_clamp(step_cfg.get("velocity", base_vel) or base_vel, 1, 127))
                    gate_factor = float(_clamp(step_cfg.get("gate", 100) or 100, 0.0, 400.0)) / 100.0
                    onset = float(group_start + i * step)
                    if shuffle_enabled and step_idx < shuffle_steps and (i % 2 == 1):
                        onset += step * 0.10
                    length = float(max(0.03125, step * gate * gate_factor))
                    if event_kind == "chord":
                        for pitch in list(event_payload):
                            nn = template.clone()
                            nn.start_beats = onset
                            nn.length_beats = length
                            nn.pitch = int(_clamp_midi(int(pitch) + transpose))
                            nn.velocity = vel_step
                            result.append(nn)
                    else:
                        seq_payload = list(event_payload)
                        pitch = seq_payload[i % len(seq_payload)]
                        nn = template.clone()
                        nn.start_beats = onset
                        nn.length_beats = length
                        nn.pitch = int(_clamp_midi(int(pitch) + transpose))
                        nn.velocity = vel_step
                        result.append(nn)

            try:
                result.sort(key=lambda n: (float(getattr(n, "start_beats", 0.0)), int(getattr(n, "pitch", 0))))
            except Exception:
                pass
            return result

        # Apply devices in chain order
        for dev in devices:
            if not isinstance(dev, dict):
                continue
            if dev.get("enabled", True) is False:
                continue

            pid = str(dev.get("plugin_id") or dev.get("type") or "")
            params = dev.get("params") if isinstance(dev.get("params"), dict) else {}
            dev_id = str(dev.get("id") or pid)

            if pid == "chrono.note_fx.arp":
                out_notes = _apply_arp(out_notes, params, dev_id)
                continue

            # per-note transforms (can expand notes)
            next_notes: List[Any] = []
            for n in out_notes:
                try:
                    base_p = int(getattr(n, "pitch", 60) or 60)
                    base_v = int(getattr(n, "velocity", 100) or 100)
                    pairs = [(base_p, base_v)]

                    if pid == "chrono.note_fx.transpose":
                        semi = int(params.get("semitones", 0) or 0)
                        pairs = [(int(_clamp_midi(p + semi)), v) for p, v in pairs]

                    elif pid == "chrono.note_fx.velocity_scale":
                        sc = float(params.get("scale", 1.0) or 1.0)
                        pairs = [(p, int(_clamp(v * sc, 0, 127))) for p, v in pairs]

                    elif pid == "chrono.note_fx.scale_snap":
                        root = int(params.get("root", 0) or 0)
                        scale = str(params.get("scale", "major") or "major")
                        mode = str(params.get("mode", "nearest") or "nearest")
                        pairs = [(_snap_pitch_to_scale(p, root, scale, mode), v) for p, v in pairs]

                    elif pid == "chrono.note_fx.chord":
                        chord = str(params.get("chord", "maj") or "maj")
                        voicing = str(params.get("voicing", "close") or "close").strip().lower()
                        spread = int(_clamp(params.get("spread", 0) or 0, -24, 24))
                        intervals = list(_CHORD_INTERVALS.get(chord, _CHORD_INTERVALS["maj"]))

                        # v644: Apply voicing transformations
                        if voicing == "drop2" and len(intervals) >= 3:
                            # Drop-2: move 2nd-from-top note down an octave
                            sorted_iv = sorted(intervals)
                            if len(sorted_iv) >= 3:
                                drop_idx = -2
                                sorted_iv[drop_idx] = sorted_iv[drop_idx] - 12
                                intervals = sorted(sorted_iv)
                        elif voicing == "drop3" and len(intervals) >= 4:
                            # Drop-3: move 3rd-from-top note down an octave
                            sorted_iv = sorted(intervals)
                            if len(sorted_iv) >= 4:
                                drop_idx = -3
                                sorted_iv[drop_idx] = sorted_iv[drop_idx] - 12
                                intervals = sorted(sorted_iv)
                        elif voicing == "open":
                            # Open voicing: alternate notes up an octave
                            sorted_iv = sorted(intervals)
                            new_iv = []
                            for idx, iv in enumerate(sorted_iv):
                                if idx % 2 == 1:
                                    new_iv.append(iv + 12)
                                else:
                                    new_iv.append(iv)
                            intervals = new_iv
                        elif voicing == "spread_wide":
                            # Spread: fan notes outward from center
                            n_iv = len(intervals)
                            center = sum(intervals) / max(1, n_iv)
                            intervals = [int(round(center + (iv - center) * 2.0)) for iv in intervals]

                        expanded = []
                        for p, v in pairs:
                            for i, itv in enumerate(intervals):
                                note_spread = spread * i if i > 0 else 0
                                expanded.append((int(_clamp_midi(int(p) + int(itv) + note_spread)), int(v)))
                        pairs = expanded

                    elif pid == "chrono.note_fx.random":
                        pr = int(params.get("pitch_range", 0) or 0)
                        vr = int(params.get("vel_range", 0) or 0)
                        prob = float(params.get("prob", 1.0) or 1.0)
                        tr = float(params.get("timing_range", 0.0) or 0.0)  # v644: beats
                        lr = float(params.get("length_range", 0.0) or 0.0)  # v644: fraction
                        pr = int(_clamp(pr, 0, 24))
                        vr = int(_clamp(vr, 0, 127))
                        prob = float(_clamp(prob, 0.0, 1.0))
                        tr = float(_clamp(tr, 0.0, 0.5))
                        lr = float(_clamp(lr, 0.0, 1.0))

                        seed = _stable_seed_int(f"{dev_id}|{getattr(n, 'start_beats', 0.0)}|{base_p}|{base_v}")
                        rnd = random.Random(seed)
                        if rnd.random() <= prob:
                            if pr:
                                base_p2 = int(_clamp_midi(base_p + rnd.randint(-pr, pr)))
                            else:
                                base_p2 = base_p
                            if vr:
                                base_v2 = int(_clamp(base_v + rnd.randint(-vr, vr), 0, 127))
                            else:
                                base_v2 = base_v
                            pairs = [(base_p2, base_v2)]
                            # v644: timing randomization
                            if tr > 0.0:
                                t_off = rnd.uniform(-tr, tr)
                                new_start = float(getattr(n, 'start_beats', 0.0)) + t_off
                                n.start_beats = max(0.0, new_start)
                            # v644: length randomization
                            if lr > 0.0:
                                orig_len = float(getattr(n, 'length_beats', 0.125))
                                l_factor = 1.0 + rnd.uniform(-lr, lr)
                                n.length_beats = max(0.03125, orig_len * l_factor)

                    # v0.0.20.644: Velocity Curve (compress/expand/limit)
                    elif pid == "chrono.note_fx.velocity_curve":
                        curve_type = str(params.get("type", "compress") or "compress").strip().lower()
                        amount = float(_clamp(params.get("amount", 0.5) or 0.5, 0.0, 1.0))
                        vel_min = int(_clamp(params.get("min", 1) or 1, 1, 127))
                        vel_max = int(_clamp(params.get("max", 127) or 127, 1, 127))
                        fixed_vel = int(_clamp(params.get("fixed", 0) or 0, 0, 127))

                        new_pairs = []
                        for p, v in pairs:
                            nv = float(v) / 127.0  # normalize 0..1
                            if curve_type == "compress":
                                # Compress toward center (0.5)
                                nv = nv + (0.5 - nv) * amount
                            elif curve_type == "expand":
                                # Expand away from center
                                nv = 0.5 + (nv - 0.5) * (1.0 + amount * 3.0)
                            elif curve_type == "limit":
                                # Hard clip to min/max
                                pass  # applied below
                            elif curve_type == "fixed":
                                # All notes same velocity
                                if fixed_vel > 0:
                                    nv = float(fixed_vel) / 127.0
                            elif curve_type == "soft":
                                # Soft curve (logarithmic feel)
                                import math as _m
                                nv = _m.pow(nv, max(0.2, 1.0 - amount))
                            elif curve_type == "hard":
                                # Hard curve (exponential feel)
                                import math as _m
                                nv = _m.pow(nv, 1.0 + amount * 2.0)
                            v_out = int(_clamp(round(nv * 127.0), vel_min, vel_max))
                            new_pairs.append((p, v_out))
                        pairs = new_pairs

                    # v0.0.20.644: Note Echo (MIDI delay/echo)
                    elif pid == "chrono.note_fx.note_echo":
                        delay_beats = float(_clamp(params.get("delay_beats", 0.5) or 0.5, 0.0625, 4.0))
                        repeats = int(_clamp(params.get("repeats", 3) or 3, 1, 16))
                        feedback = float(_clamp(params.get("feedback", 0.6) or 0.6, 0.0, 1.0))
                        transpose_per = int(params.get("transpose_per_repeat", 0) or 0)
                        transpose_per = int(_clamp(transpose_per, -24, 24))

                        # First note = original
                        expanded = list(pairs)
                        for rep in range(1, repeats + 1):
                            vel_factor = feedback ** rep
                            if vel_factor < 0.01:
                                break
                            for p, v in pairs:
                                echo_p = int(_clamp_midi(p + transpose_per * rep))
                                echo_v = int(_clamp(round(v * vel_factor), 1, 127))
                                # Create echo note with offset timing
                                nn = n.clone()
                                nn.pitch = echo_p
                                nn.velocity = echo_v
                                nn.start_beats = float(getattr(n, 'start_beats', 0.0)) + delay_beats * rep
                                nn.length_beats = float(getattr(n, 'length_beats', 0.125))
                                next_notes.append(nn)
                        pairs = expanded  # original pairs go through normal emit

                    # emit notes for each pair
                    for p, v in pairs:
                        nn = n.clone()
                        nn.pitch = int(_clamp_midi(int(p)))
                        nn.velocity = int(_clamp(int(v), 0, 127))
                        next_notes.append(nn)
                except Exception:
                    # fallback: keep original note
                    next_notes.append(n)

            out_notes = next_notes

        return out_notes
    except Exception:
        return list(notes)
