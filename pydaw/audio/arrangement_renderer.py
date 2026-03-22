"""Arrangement renderer for JACK/sounddevice.

Pure-numpy renderer that mixes prepared audio (and rendered MIDI->WAV) clips
into an output buffer for a given playhead position.

Design goals:
- No Qt usage here (service-layer friendly)
- Preparation (file IO / FluidSynth renders) happens *outside* realtime callbacks
- Rendering is a tight function operating on numpy arrays
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import math

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    import soundfile as sf
except Exception:  # pragma: no cover
    sf = None

from .midi_render import RenderKey, ensure_rendered_wav
from .note_expression_eval import effective_velocity, should_play_note, effective_micropitch_note_start

from .note_fx_chain import (
    apply_note_fx_chain_to_notes,
    apply_note_fx_chain_to_pitch_velocity,
    note_fx_chain_signature,
)

try:
    from .arranger_cache import ArrangerRenderCache, DEFAULT_ARRANGER_CACHE
except Exception:  # pragma: no cover
    ArrangerRenderCache = None  # type: ignore
    DEFAULT_ARRANGER_CACHE = None  # type: ignore

try:
    from .time_stretch import time_stretch_stereo, time_stretch_stereo_mode
except Exception:  # pragma: no cover
    time_stretch_stereo = None  # type: ignore
    time_stretch_stereo_mode = None  # type: ignore

from .ring_buffer import MAX_TRACKS



def _midi_notes_content_hash(notes) -> str:  # noqa: ANN001
    """Stable content hash for prepared notes.

    MUST include expressions, otherwise expression edits won't invalidate caches
    and the user would hear no change.
    """
    import hashlib
    import json

    def _get(n: Any, key: str, default: Any):
        if isinstance(n, dict):
            return n.get(key, default)
        return getattr(n, key, default)

    h = hashlib.sha1()
    include_params = ("velocity", "chance", "timbre", "pressure", "micropitch")

    for n in (notes or []):
        try:
            pitch = int(_get(n, "pitch", 0))
            sb = float(_get(n, "start_beats", _get(n, "start", 0.0)))
            lb = float(_get(n, "length_beats", _get(n, "length", 0.0)))
            vel = int(_get(n, "velocity", 0))
        except Exception:
            continue

        h.update(f"{pitch}:{sb:.6f}:{lb:.6f}:{vel};".encode("utf-8"))

        expr = _get(n, "expressions", None)
        if isinstance(expr, dict):
            filtered = {k: expr.get(k) for k in include_params if k in expr}
            try:
                h.update(json.dumps(filtered, sort_keys=True, separators=(',', ':')).encode("utf-8"))
            except Exception:
                pass

    return h.hexdigest()[:16]



@dataclass
class _NoteObj:
    """Lightweight note object used for rendering.

    We keep audio-layer code independent from UI/model specifics while still
    offering attribute-style access expected by midi_render.ensure_rendered_wav().

    IMPORTANT: We must preserve expressions so that playback/render caches are
    invalidated and note-on behavior can use velocity/chance.
    """
    pitch: int
    start_beats: float
    length_beats: float
    velocity: int = 100
    expressions: Dict[str, Any] = field(default_factory=dict)
    expression_curve_types: Dict[str, Any] = field(default_factory=dict)



def _coerce_notes(notes: Any) -> List[_NoteObj]:
    """Coerce notes (dicts or objects) into a list of _NoteObj."""
    out: List[_NoteObj] = []

    def _get(n: Any, key: str, default: Any):
        if isinstance(n, dict):
            return n.get(key, default)
        return getattr(n, key, default)

    for n in list(notes or []):
        try:
            pitch = int(_get(n, "pitch", 0))
            sb = float(_get(n, "start_beats", _get(n, "start", 0.0)))
            lb = float(_get(n, "length_beats", _get(n, "length", 0.0)))
            vel = int(_get(n, "velocity", 100))
        except Exception:
            continue
        out.append(_NoteObj(pitch=pitch, start_beats=sb, length_beats=lb, velocity=vel,
                    expressions=_get(n, 'expressions', {}) if isinstance(_get(n, 'expressions', {}), dict) else {},
                    expression_curve_types=_get(n, 'expression_curve_types', {}) if isinstance(_get(n, 'expression_curve_types', {}), dict) else {}))
    return out


def _apply_ties_to_notes(project: Any, clip_id: str, notes: Any) -> List[_NoteObj]:
    """Apply notation 'tie' markers to notes for playback/rendering.

    Ties are stored as notation_marks in the project model:

        {type: "tie", data: {"from": {"beat": .., "pitch": ..}, "to": {...}}}

    Behavior:
    - For each pitch, follow tie chains (from -> to -> ...).
    - Merge chained notes into the first note by extending its length so that
      the *end* equals the end of the last note in the chain.
    - Remove the subsequent notes from rendering to avoid re-triggering.

    This keeps MIDI playback aligned with classical notation expectations while
    staying non-destructive: the project note list is not mutated here.
    """

    def r6(x: float) -> float:
        try:
            return round(float(x), 6)
        except Exception:
            return 0.0

    coerced = _coerce_notes(notes)
    if not coerced:
        return []

    # Collect tie marks for this clip
    try:
        marks = getattr(project, "notation_marks", []) or []
    except Exception:
        marks = []
    if not isinstance(marks, list):
        marks = []

    ties = []
    for m in marks:
        try:
            if str(m.get("clip_id", "")) != str(clip_id):
                continue
            if str(m.get("type", "")) != "tie":
                continue
            d = m.get("data", {}) or {}
            a = d.get("from", {}) or {}
            b = d.get("to", {}) or {}
            pitch = int(a.get("pitch", b.get("pitch", 0)))
            bf = r6(float(a.get("beat", 0.0)))
            bt = r6(float(b.get("beat", 0.0)))
            if pitch < 0 or pitch > 127:
                continue
            if abs(bt - bf) < 1e-9:
                continue
            ties.append((pitch, bf, bt))
        except Exception:
            continue

    if not ties:
        return coerced

    # Map notes by (pitch, start_beats rounded)
    note_idx = {}
    for i, n in enumerate(coerced):
        note_idx[(int(n.pitch), r6(n.start_beats))] = i

    # Build per-pitch next map
    next_map: Dict[int, Dict[float, float]] = {}
    for pitch, bf, bt in ties:
        # normalize ordering: tie connects earlier -> later
        a, b = (bf, bt) if bf < bt else (bt, bf)
        next_map.setdefault(int(pitch), {})[r6(a)] = r6(b)

    # Find chain starts for each pitch
    remove_idx = set()
    for pitch, mapping in next_map.items():
        if not mapping:
            continue
        starts = set(mapping.keys())
        targets = set(mapping.values())
        chain_starts = [s for s in starts if s not in targets]
        if not chain_starts:
            # potential loop; still try arbitrary deterministic start
            chain_starts = sorted(list(starts))[:1]

        for s0 in sorted(chain_starts):
            # follow chain
            chain = [r6(s0)]
            seen = set(chain)
            cur = r6(s0)
            for _ in range(128):
                nxt = mapping.get(cur)
                if nxt is None:
                    break
                nxt = r6(nxt)
                if nxt in seen:
                    break
                chain.append(nxt)
                seen.add(nxt)
                cur = nxt

            if len(chain) < 2:
                continue

            # Resolve chain notes
            idxs = []
            ok = True
            for beat in chain:
                i = note_idx.get((int(pitch), r6(beat)))
                if i is None:
                    ok = False
                    break
                idxs.append(int(i))
            if not ok:
                continue

            idxs = list(dict.fromkeys(idxs))  # unique in order
            if len(idxs) < 2:
                continue

            i0 = idxs[0]
            if i0 in remove_idx:
                continue

            # Determine final end beat (max end among chain)
            end_beat = 0.0
            for ii in idxs:
                n = coerced[ii]
                end_beat = max(end_beat, float(n.start_beats) + max(0.0, float(n.length_beats)))

            n0 = coerced[i0]
            new_len = max(0.0, float(end_beat) - float(n0.start_beats))
            if new_len > float(n0.length_beats) + 1e-9:
                coerced[i0] = _NoteObj(
                    pitch=int(n0.pitch),
                    start_beats=float(n0.start_beats),
                    length_beats=float(new_len),
                    velocity=int(n0.velocity),
                )

            for ii in idxs[1:]:
                remove_idx.add(int(ii))

    out = [n for i, n in enumerate(coerced) if i not in remove_idx]
    out.sort(key=lambda n: (float(n.start_beats), int(n.pitch)))
    return out



@dataclass
class PreparedClip:
    start_sample: int
    end_sample: int
    offset_sample: int
    data: "np.ndarray"  # (n, 2)
    gain_l: float  # clip-level gain L (track gain is applied later)
    gain_r: float  # clip-level gain R
    track_idx: int  # deterministic track index (matches HybridBridge mapping)


@dataclass
class PreparedMidiEvent:
    """v0.0.20.42: A scheduled MIDI event for sampler-based instrument tracks.

    Instead of pre-rendering MIDI through FluidSynth, these events are
    processed in real-time by the audio callback, which triggers the
    sampler engine for note_on/note_off. This gives Pro-DAW-like behavior:
    the sampler responds live to MIDI notes from the arrangement.
    """
    sample_pos: int       # absolute sample position
    is_note_on: bool      # True=note_on, False=note_off
    pitch: int            # MIDI pitch (0-127)
    velocity: int         # MIDI velocity (0-127, 0 for note_off)
    track_id: str         # track ID for sampler registry lookup
    pitch_offset_semitones: float = 0.0  # safe v1 MPE-mode: note-start micropitch only
    # --- MPE v2: continuous micropitch curve ---
    micropitch_curve: list = field(default_factory=list)  # [(t_norm, semitones), ...] for continuous bend
    note_duration_samples: int = 0  # total note length in samples (for t normalization in pull)

def _pan_gains(vol: float, pan: float) -> Tuple[float, float]:
    pan = max(-1.0, min(1.0, float(pan)))
    angle = (pan + 1.0) * (math.pi / 4.0)
    return float(vol) * math.cos(angle), float(vol) * math.sin(angle)


def _auto_val_to_gain(val: float) -> float:
    """Map normalized automation value (0..1) to gain multiplier.

    0.0 = silence (0x)
    0.5 = unity gain (1x)
    1.0 = +12 dB (~4x)
    """
    v = max(0.0, min(1.0, float(val)))
    if v <= 0.5:
        # 0..0.5 -> 0..1 (linear)
        return v * 2.0
    else:
        # 0.5..1.0 -> 1..4 (exponential, +12dB max)
        t = (v - 0.5) * 2.0  # 0..1
        return 1.0 + t * t * 3.0  # 1..4

def _coerce_warp_markers(raw: Any, clip_len_beats: float) -> List[Tuple[float, float]]:
    """Coerce stretch_markers into a sorted list of (src_beat, dst_beat).

    Supported formats:
    - legacy: [float, float, ...]  -> treated as identity markers (src=dst)
    - current: [{"src":..,"dst":..}, ...]

    Endpoints (0,0) and (L,L) are always added as anchors.
    """
    L = max(1e-6, float(clip_len_beats))
    pts: List[Tuple[float, float]] = []
    for m in list(raw or []):
        if isinstance(m, dict):
            try:
                src = float(m.get('src', m.get('beat', 0.0)))
                dst = float(m.get('dst', m.get('beat', src)))
            except Exception:
                continue
            pts.append((src, dst))
        elif isinstance(m, (int, float)):
            fv = float(m)
            pts.append((fv, fv))

    # Add anchors
    pts.append((0.0, 0.0))
    pts.append((L, L))

    # Sort by src and clamp dst to be monotonic (no crossing)
    pts = [(max(0.0, min(L, s)), max(0.0, min(L, d))) for s, d in pts]
    pts.sort(key=lambda t: t[0])

    # Remove duplicate src (keep the last one)
    merged: List[Tuple[float, float]] = []
    for s, d in pts:
        if merged and abs(merged[-1][0] - s) < 1e-4:
            merged[-1] = (s, d)
        else:
            merged.append((s, d))

    # Clamp dst between neighbors
    out: List[Tuple[float, float]] = []
    last_d = None
    for i, (s, d) in enumerate(merged):
        lo = 0.0
        hi = L
        if i > 0:
            lo = out[-1][1] + 1e-3
        if i < len(merged) - 1:
            # rough upper bound from the next dst (will be refined after)
            try:
                hi = min(hi, float(merged[i + 1][1]) - 1e-3)
            except Exception:
                pass
        d2 = max(lo, min(hi, d))
        out.append((s, d2))
        last_d = d2

    # Ensure anchors exact
    out[0] = (0.0, 0.0)
    out[-1] = (L, L)
    return out


def _linear_resample_stereo(seg, out_len: int):  # noqa: ANN001
    """Fast linear resample for a stereo numpy array (N,2)."""
    if np is None:
        return seg
    try:
        n = int(seg.shape[0])
        out_len = int(max(1, out_len))
    except Exception:
        return seg
    if n <= 1 or out_len == n:
        return seg
    x_old = np.linspace(0.0, 1.0, num=n, endpoint=False, dtype=np.float64)
    x_new = np.linspace(0.0, 1.0, num=out_len, endpoint=False, dtype=np.float64)
    left = np.interp(x_new, x_old, seg[:, 0].astype(np.float64)).astype(np.float32)
    right = np.interp(x_new, x_old, seg[:, 1].astype(np.float64)).astype(np.float32)
    return np.stack([left, right], axis=1)


def _apply_warp_markers(data, clip_len_beats: float, markers_raw: Any):  # noqa: ANN001
    """Apply per-clip warp markers to already-decoded (and globally stretched) audio.

    Output length is kept identical to input length (anchors at 0 and end), so this is
    safe for existing timeline math.

    Implementation: piecewise time-stretch between marker anchors.
    """
    if np is None or data is None:
        return data
    if data.shape[0] < 64:
        return data

    L = float(max(1e-6, clip_len_beats))
    pts = _coerce_warp_markers(markers_raw, L)

    # If only anchors (no real markers), nothing to do
    if len(pts) <= 2:
        return data

    n_base = int(data.shape[0])
    out = np.zeros_like(data)

    # Convert beats -> sample indices
    src_idx = [int(round((s / L) * (n_base - 1))) for s, _ in pts]
    dst_idx = [int(round((d / L) * (n_base - 1))) for _, d in pts]

    # Ensure strictly increasing indices
    for i in range(1, len(src_idx)):
        if src_idx[i] <= src_idx[i - 1]:
            src_idx[i] = src_idx[i - 1] + 1
    for i in range(1, len(dst_idx)):
        if dst_idx[i] <= dst_idx[i - 1]:
            dst_idx[i] = dst_idx[i - 1] + 1

    src_idx[-1] = min(src_idx[-1], n_base - 1)
    dst_idx[-1] = min(dst_idx[-1], n_base - 1)

    # Build segments
    overlap = 128
    write_prev_end = 0
    for i in range(len(pts) - 1):
        s0, s1 = src_idx[i], src_idx[i + 1]
        d0, d1 = dst_idx[i], dst_idx[i + 1]
        if s1 <= s0 or d1 <= d0:
            continue
        seg = data[s0:s1].astype(np.float32, copy=False)
        desired = int(d1 - d0)
        if desired <= 1 or seg.shape[0] <= 1:
            continue

        # rate = src_len / dst_len (rate>1 => faster => shorter)
        rate = float(seg.shape[0]) / float(desired)
        seg_out = None
        if time_stretch_stereo is not None and 0.25 <= rate <= 4.0 and seg.shape[0] > 128:
            try:
                seg_out = time_stretch_stereo(seg, rate=float(rate), sr=1)
            except Exception:
                seg_out = None
        if seg_out is None:
            seg_out = _linear_resample_stereo(seg, desired)
        else:
            # Ensure exact length
            if seg_out.shape[0] != desired:
                seg_out = _linear_resample_stereo(seg_out, desired)

        # Write with short crossfade at boundaries
        if i == 0:
            out[d0:d0 + desired] = seg_out[:desired]
            write_prev_end = d0 + desired
        else:
            # crossfade with existing out at d0
            ov = min(overlap, desired, d0)
            if ov > 4:
                a = np.linspace(0.0, 1.0, num=ov, dtype=np.float32)[:, None]
                out[d0 - ov:d0] = out[d0 - ov:d0] * (1.0 - a) + seg_out[:ov] * a
                out[d0:d0 + desired - ov] = seg_out[ov:desired]
            else:
                out[d0:d0 + desired] = seg_out[:desired]
            write_prev_end = d0 + desired

    return out



def prepare_clips(project: Any, sr: int, cache: Optional["ArrangerRenderCache"] = None) -> Tuple[List[PreparedClip], List[PreparedMidiEvent], float]:
    """Prepare all playable clips for rendering.

    Returns (prepared_clips, midi_events, bpm).
    v0.0.20.42: midi_events for sampler-based instrument tracks (no SF2).
    """
    if np is None or sf is None:
        return ([], [], float(getattr(project, "bpm", 120.0) or 120.0))

    # Shared cache is optional. If provided, it must be thread-safe.
    if cache is None:
        try:
            cache = DEFAULT_ARRANGER_CACHE  # type: ignore
        except Exception:
            cache = None

    bpm = float(getattr(project, "bpm", getattr(project, "tempo_bpm", 120.0)) or 120.0)
    beats_per_second = bpm / 60.0
    samples_per_beat = sr / max(1e-9, beats_per_second)

    def beats_to_samples(beats: float) -> int:
        return int(round(float(beats) * samples_per_beat))

    tracks_by_id = {t.id: t for t in getattr(project, "tracks", []) or []}

    # Deterministic track index mapping (matches GUI track order).
    # NOTE: We keep *all* tracks in the map (including master) to keep indices stable.
    # The audio thread will apply mute/solo/vol/pan in real-time via TrackParamState.
    tracks_in_order = list(getattr(project, "tracks", []) or [])
    track_idx_map = {t.id: int(i) for i, t in enumerate(tracks_in_order)}

    prepared: List[PreparedClip] = []
    midi_events: List[PreparedMidiEvent] = []

    for clip in getattr(project, "clips", []) or []:
        # v0.0.20.588: Skip launcher-only clips (they play via ClipLauncherPlaybackService)
        if getattr(clip, 'launcher_only', False):
            continue
        kind = str(getattr(clip, "kind", "") or "")
        track = tracks_by_id.get(getattr(clip, "track_id", ""))
        if not track:
            continue

        # Determine deterministic track index for per-track rendering/metering.
        track_idx = int(track_idx_map.get(track.id, 0))
        if track_idx < 0:
            track_idx = 0
        if track_idx >= MAX_TRACKS:
            # Avoid out-of-bounds in TrackParamState/track buffers.
            continue

        data = None
        cache_path: Optional[str] = None
        effective_rate: float = 1.0

        if kind == "audio":
            path = getattr(clip, "source_path", None)
            if not path:
                continue

            cache_path = str(path)

            # Determine effective play-rate for tempo sync (pitch-preserving stretch)
            source_bpm = float(getattr(clip, "source_bpm", 0.0) or 0.0)
            user_stretch = float(getattr(clip, "stretch", 1.0) or 1.0)
            tempo_ratio = (bpm / source_bpm) if (source_bpm and source_bpm > 0.0) else 1.0
            effective_rate = float(tempo_ratio) / max(1e-6, float(user_stretch))

            # Read/Resample via cache if available
            if cache is not None:
                data = cache.get_decoded(cache_path, int(sr))
            if data is None:
                try:
                    data, file_sr = sf.read(path, dtype="float32", always_2d=True)
                except Exception:
                    continue
                if data.shape[1] == 1:
                    data = np.repeat(data, 2, axis=1)
                elif data.shape[1] >= 2:
                    data = data[:, :2]
                if int(file_sr or sr) != int(sr) and data.shape[0] > 1:
                    # naive resample
                    ratio = float(sr) / float(file_sr)
                    n_out = max(1, int(round(data.shape[0] * ratio)))
                    x_old = np.linspace(0.0, 1.0, num=data.shape[0], endpoint=False)
                    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
                    data = np.vstack([
                        np.interp(x_new, x_old, data[:, 0]),
                        np.interp(x_new, x_old, data[:, 1]),
                    ]).T.astype(np.float32, copy=False)

            # Apply tempo sync (if available). NEVER in realtime callback – this is pre-render.
            if (
                data is not None
                and 0.25 <= float(effective_rate) <= 4.0
                and abs(float(effective_rate) - 1.0) > 1e-3
                and data.shape[0] > 8
                and time_stretch_stereo is not None
            ):
                if cache is not None and cache_path is not None:
                    stretched = cache.get_stretched(cache_path, int(sr), float(effective_rate))
                    if stretched is not None:
                        data = stretched
                else:
                    try:
                        # v0.0.20.641: Use stretch_mode from clip (AP3 Phase 3B)
                        _smode = str(getattr(clip, 'stretch_mode', 'tones') or 'tones')
                        _onsets = list(getattr(clip, 'onsets', []) or [])
                        if time_stretch_stereo_mode is not None and _smode != 'tones':
                            data = time_stretch_stereo_mode(data, rate=float(effective_rate), mode=_smode, sr=int(sr), onsets=_onsets or None)
                        else:
                            data = time_stretch_stereo(data, rate=float(effective_rate), sr=int(sr))
                    except Exception:
                        effective_rate = 1.0

        elif kind == "midi":
            # v0.0.20.48: Plugin-type based routing (Pro-DAW-Style!)
            # Check which instrument plugin this track uses
            
            plugin_type = getattr(track, "plugin_type", None)
            is_instrument = str(getattr(track, "kind", "")) == "instrument"

            # v0.0.20.80: Instrument Power/Bypass — skip if disabled
            if not bool(getattr(track, "instrument_enabled", True)):
                continue
            
            # Backwards compatibility: Auto-detect plugin_type from sf2_path
            if not plugin_type and is_instrument:
                sf2_path = getattr(track, "sf2_path", None)
                if sf2_path:
                    plugin_type = "sf2"
                # NOTE: We do NOT check project.default_sf2 here!
                # Each track must have explicit plugin_type or sf2_path.
            
            notes_map: Dict[str, Any] = getattr(project, "midi_notes", {}) or {}
            notes_raw = notes_map.get(getattr(clip, "id", ""), [])
            # Apply notation tie markers for playback (non-destructive).
            notes = _apply_ties_to_notes(project, str(getattr(clip, "id", "")), notes_raw)
            if not notes:
                continue

            # LIVE MIDI PATH — for any non-SF2 instrument track we dispatch MIDI
            # in real-time to the registered instrument engine (Sampler, Drum Machine,
            # or future plugins). If no engine is registered for the track_id, these
            # events are simply ignored at runtime.
            if is_instrument and plugin_type != "sf2":
                clip_start_beats = float(getattr(clip, "start_beats", 0.0) or 0.0)
                track_id = str(getattr(track, "id", ""))

                def _nget(n: Any, key: str, default: Any = 0.0) -> Any:
                    if isinstance(n, dict):
                        return n.get(key, default)
                    return getattr(n, key, default)


                # v0.0.20.60: Apply NOTE-FX chain (MIDI before instrument) to the whole note list
                try:
                    chain = getattr(track, "note_fx_chain", None)
                    fx_notes = apply_note_fx_chain_to_notes(notes, chain)
                except Exception:
                    fx_notes = notes

                for n in (fx_notes or []):
                    # Support both dict-formats and MidiNote objects.
                    try:
                        note_start = float(_nget(n, "start_beats", _nget(n, "start", 0.0)))
                        note_length = float(_nget(n, "length_beats", _nget(n, "length", 0.0)))
                        pitch = int(_nget(n, "pitch", 60))
                        vel = int(_nget(n, "velocity", 100))
                        # Note Expressions: velocity/chance at note-on (safe)
                        try:
                            abs_start_for_chance = float(clip_start_beats + note_start)
                        except Exception:
                            abs_start_for_chance = float(note_start)
                        try:
                            if not should_play_note(clip_id=str(getattr(clip, "id", "")), note=n, abs_start_beats=abs_start_for_chance):
                                continue
                        except Exception:
                            pass
                        try:
                            vel = int(effective_velocity(n))
                        except Exception:
                            pass
                    except Exception:
                        continue

                    abs_start_beat = float(clip_start_beats + note_start)
                    abs_end_beat = float(abs_start_beat + max(0.125, float(note_length)))

                    on_sample = beats_to_samples(abs_start_beat)
                    off_sample = beats_to_samples(abs_end_beat)

                    pitch_off = 0.0
                    _mpe_curve = []
                    _note_dur_samples = 0
                    try:
                        from pydaw.core.settings_store import get_settings  # type: ignore
                        _qs = get_settings()
                        _mpe = str(_qs.value("audio/note_expr_mpe_mode", False)).strip().lower() in ("1", "true", "yes", "on")
                    except Exception:
                        _mpe = False
                    if _mpe:
                        try:
                            pitch_off = float(effective_micropitch_note_start(n) or 0.0)
                        except Exception:
                            pitch_off = 0.0
                        # MPE v2: pass full curve for continuous bend
                        try:
                            from .note_expression_eval import micropitch_curve_points
                            _mpe_curve = micropitch_curve_points(n, steps=24)
                            if _mpe_curve:
                                _note_dur_samples = max(1, off_sample - on_sample)
                        except Exception:
                            _mpe_curve = []

                    midi_events.append(PreparedMidiEvent(
                        sample_pos=on_sample, is_note_on=True,
                        pitch=pitch, velocity=vel,
                        track_id=track_id, pitch_offset_semitones=float(pitch_off),
                        micropitch_curve=list(_mpe_curve),
                        note_duration_samples=int(_note_dur_samples),
                    ))
                    midi_events.append(PreparedMidiEvent(
                        sample_pos=off_sample, is_note_on=False,
                        pitch=pitch, velocity=0,
                        track_id=track_id,
                    ))
                continue  # Skip FluidSynth/offline path for this clip

            # SF2 PATH — FluidSynth offline rendering
            if plugin_type != "sf2":
                # Not an SF2 instrument → skip
                continue
            
            # Get SF2 path for this track
            sf2 = getattr(track, "sf2_path", None)
            if not sf2:
                # No SF2 on this track → skip
                continue

            # RenderKey muss zu midi_render.RenderKey passen (wird als stabiler Cache-Key genutzt).
            sf2_bank = int(getattr(track, "sf2_bank", 0) or 0)
            sf2_preset = int(getattr(track, "sf2_preset", 0) or 0)
            clip_length_beats = float(getattr(clip, "length_beats", 0.0) or 0.0)
            if clip_length_beats <= 0.0:
                # Fallback: Länge aus Notes ableiten (max (start+length))
                try:
                    def _get(n: Any, key: str, default: Any = 0.0) -> Any:
                        if isinstance(n, dict):
                            return n.get(key, default)
                        return getattr(n, key, default)

                    def _note_end(n: Any) -> float:
                        # Support both dict-formats and MidiNote objects.
                        start = float(_get(n, "start_beats", _get(n, "start", 0.0)))
                        length = float(_get(n, "length_beats", _get(n, "length", 0.0)))
                        return max(0.0, start + max(0.0, length))

                    clip_length_beats = max(_note_end(n) for n in (notes or []))
                except Exception:
                    clip_length_beats = 0.0

            # Guarantee a non-zero clip length (older projects may not store it).
            if clip_length_beats <= 0.0:
                clip_length_beats = 4.0

            # Content hash: supports MidiNote objects (start_beats/length_beats)
            notes_fx = apply_note_fx_chain_to_notes(notes, getattr(track, "note_fx_chain", None))
            content_hash = f"{_midi_notes_content_hash(notes_fx)}:{note_fx_chain_signature(getattr(track, 'note_fx_chain', None))}"
            key = RenderKey(
                clip_id=str(getattr(clip, "id", "")),
                sf2_path=str(sf2),
                sf2_bank=int(sf2_bank),
                sf2_preset=int(sf2_preset),
                bpm=float(bpm),
                samplerate=int(sr),
                clip_length_beats=float(clip_length_beats),
                content_hash=str(content_hash),
            )
            try:
                wav_path = ensure_rendered_wav(
                    key=key,
                    midi_notes=list(notes_fx or []),
                    clip_start_beats=float(getattr(clip, "start_beats", 0.0) or 0.0),
                    clip_length_beats=float(clip_length_beats),
                )
                if not wav_path:
                    continue
                cache_path = wav_path.as_posix()

                # IMPORTANT: when we load from cache, the decoded audio is already at the
                # target sample rate. If we don't initialize file_sr here, Python can raise
                # UnboundLocalError later when file_sr is referenced.
                file_sr = int(sr)

                if cache is not None:
                    data = cache.get_decoded(cache_path, int(sr))
                if data is None:
                    data, file_sr = sf.read(cache_path, dtype="float32", always_2d=True)
            except Exception:
                continue

            # If we bypassed cache, normalize/resample now.
            if data is not None and data.shape[1] == 1:
                data = np.repeat(data, 2, axis=1)
            elif data is not None:
                data = data[:, :2]
            if data is not None and int(file_sr or sr) != int(sr) and data.shape[0] > 1:
                ratio = float(sr) / float(file_sr)
                n_out = max(1, int(round(data.shape[0] * ratio)))
                x_old = np.linspace(0.0, 1.0, num=data.shape[0], endpoint=False)
                x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
                data = np.vstack([
                    np.interp(x_new, x_old, data[:, 0]),
                    np.interp(x_new, x_old, data[:, 1]),
                ]).T.astype(np.float32, copy=False)

            # Optional manual stretch for MIDI renders (clip.stretch), kept compatible.
            user_stretch = float(getattr(clip, "stretch", 1.0) or 1.0)
            effective_rate = 1.0 / max(1e-6, float(user_stretch))
            if (
                data is not None
                and 0.25 <= float(effective_rate) <= 4.0
                and abs(float(effective_rate) - 1.0) > 1e-3
                and data.shape[0] > 8
                and time_stretch_stereo is not None
            ):
                if cache is not None and cache_path is not None:
                    stretched = cache.get_stretched(cache_path, int(sr), float(effective_rate))
                    if stretched is not None:
                        data = stretched
                else:
                    try:
                        # v0.0.20.641: Use stretch_mode from clip (AP3 Phase 3B)
                        _smode2 = str(getattr(clip, 'stretch_mode', 'tones') or 'tones')
                        if time_stretch_stereo_mode is not None and _smode2 != 'tones':
                            data = time_stretch_stereo_mode(data, rate=float(effective_rate), mode=_smode2, sr=int(sr))
                        else:
                            data = time_stretch_stereo(data, rate=float(effective_rate), sr=int(sr))
                    except Exception:
                        effective_rate = 1.0
        else:
            continue

        if data is None:
            continue

        

        # ── Warp Markers (Bitwig-style) ──
        # If clip.stretch_markers are present, apply piecewise warp *after* global tempo sync stretch.
        try:
            if kind == "audio":
                wm = getattr(clip, 'stretch_markers', None)
                if wm:
                    data = _apply_warp_markers(data, float(getattr(clip, 'length_beats', 0.0) or clip_len_beats or 4.0), wm)
        except Exception:
            pass
# ── Skip muted clips ──
        if bool(getattr(clip, "muted", False)):
            continue

        # ── Reverse playback (non-destructive) ──
        # Flip audio data when clip.reversed is True (Bitwig/Ableton-style).
        if bool(getattr(clip, "reversed", False)) and data is not None and data.shape[0] > 1:
            data = data[::-1].copy()

        # Offsets/length
        offset_s = float(getattr(clip, "offset_seconds", 0.0) or 0.0)
        # Offset maps from source-time to stretched-time: t_out = t_in / rate
        offset_sample = max(0, int(round((offset_s * float(sr)) / max(1e-6, float(effective_rate)))))

        start_sample = beats_to_samples(float(getattr(clip, "start_beats", 0.0) or 0.0))
        clip_len_beats = float(getattr(clip, "length_beats", 0.0) or 0.0)
        if clip_len_beats <= 0:
            clip_len_samples = max(0, int(data.shape[0] - offset_sample))
        else:
            clip_len_samples = beats_to_samples(clip_len_beats)

        end_sample = start_sample + max(0, int(clip_len_samples))

        # ── Fade In/Out (non-destructive, applied to data copy) ──
        fade_in_beats = float(getattr(clip, "fade_in_beats", 0.0) or 0.0)
        fade_out_beats = float(getattr(clip, "fade_out_beats", 0.0) or 0.0)
        if (fade_in_beats > 0.001 or fade_out_beats > 0.001) and data.shape[0] > 1:
            data = data.copy()  # non-destructive
            total_samples = data.shape[0]
            if fade_in_beats > 0.001:
                fade_in_samples = min(total_samples, beats_to_samples(fade_in_beats))
                if fade_in_samples > 0:
                    ramp = np.linspace(0.0, 1.0, num=fade_in_samples, dtype=np.float32)
                    data[:fade_in_samples, 0] *= ramp
                    data[:fade_in_samples, 1] *= ramp
            if fade_out_beats > 0.001:
                fade_out_samples = min(total_samples, beats_to_samples(fade_out_beats))
                if fade_out_samples > 0:
                    ramp = np.linspace(1.0, 0.0, num=fade_out_samples, dtype=np.float32)
                    data[-fade_out_samples:, 0] *= ramp
                    data[-fade_out_samples:, 1] *= ramp

        # ── Static Pitch Shift (clip.pitch in semitones) ──
        static_pitch = float(getattr(clip, "pitch", 0.0) or 0.0)
        if abs(static_pitch) > 0.01 and data.shape[0] > 1:
            try:
                rate = 2.0 ** (static_pitch / 12.0)
                n_src = data.shape[0]
                n_out = int(n_src / rate)
                if n_out > 0:
                    src_idx = np.linspace(0, n_src - 1, num=n_out, dtype=np.float64)
                    idx_f = np.floor(src_idx).astype(np.int64)
                    idx_c = np.minimum(idx_f + 1, n_src - 1)
                    frac = (src_idx - idx_f).astype(np.float32)[:, np.newaxis]
                    resampled = data[idx_f] * (1.0 - frac) + data[idx_c] * frac
                    data = data.copy() if not (fade_in_beats > 0.001 or fade_out_beats > 0.001) else data
                    if resampled.shape[0] >= data.shape[0]:
                        data[:] = resampled[:data.shape[0]]
                    else:
                        data[:resampled.shape[0]] = resampled
                        data[resampled.shape[0]:] = 0.0
            except Exception:
                pass

        # ── Clip Automation (Gain/Pan/Pitch envelopes, Bitwig/Ableton-style) ──
        clip_auto = getattr(clip, "clip_automation", None)
        if clip_auto and isinstance(clip_auto, dict) and data.shape[0] > 1 and clip_len_beats > 0:
            data = data.copy() if not (fade_in_beats > 0.001 or fade_out_beats > 0.001) else data
            total_frames = data.shape[0]
            # Gain automation
            gain_pts = clip_auto.get("gain", [])
            if gain_pts and len(gain_pts) >= 1:
                # Build per-sample gain curve from breakpoints
                # value 0.0=silence, 0.5=unity, 1.0=+12dB
                xs = np.array([float(p.get("beat", 0)) / max(1e-6, clip_len_beats) for p in gain_pts], dtype=np.float32)
                # Map 0..1 normalized to gain: 0.0->0.0 (silence), 0.5->1.0 (unity), 1.0->4.0 (+12dB)
                ys = np.array([_auto_val_to_gain(float(p.get("value", 0.5))) for p in gain_pts], dtype=np.float32)
                xs = np.clip(xs, 0.0, 1.0)
                sample_positions = np.linspace(0.0, 1.0, num=total_frames, dtype=np.float32)
                gain_curve = np.interp(sample_positions, xs, ys).astype(np.float32)
                data[:, 0] *= gain_curve
                data[:, 1] *= gain_curve

            # Pan automation
            pan_pts = clip_auto.get("pan", [])
            if pan_pts and len(pan_pts) >= 1:
                xs = np.array([float(p.get("beat", 0)) / max(1e-6, clip_len_beats) for p in pan_pts], dtype=np.float32)
                # Map 0..1 normalized to pan: 0.0->hard left, 0.5->center, 1.0->hard right
                ys = np.array([float(p.get("value", 0.5)) * 2.0 - 1.0 for p in pan_pts], dtype=np.float32)
                xs = np.clip(xs, 0.0, 1.0)
                ys = np.clip(ys, -1.0, 1.0)
                sample_positions = np.linspace(0.0, 1.0, num=total_frames, dtype=np.float32)
                pan_curve = np.interp(sample_positions, xs, ys).astype(np.float32)
                # Equal-power pan law
                angle = (pan_curve + 1.0) * (math.pi / 4.0)
                l_gain = np.cos(angle).astype(np.float32)
                r_gain = np.sin(angle).astype(np.float32)
                data[:, 0] *= l_gain
                data[:, 1] *= r_gain

            # Pitch automation (varispeed: changes pitch via resampling)
            # Mapping: 0.0 → -12 semitones, 0.5 → 0 (unity), 1.0 → +12 semitones
            pitch_pts = clip_auto.get("pitch", [])
            if pitch_pts and len(pitch_pts) >= 1:
                xs = np.array([float(p.get("beat", 0)) / max(1e-6, clip_len_beats) for p in pitch_pts], dtype=np.float32)
                # Map 0..1 to semitones: 0.0→-12, 0.5→0, 1.0→+12
                ys = np.array([(float(p.get("value", 0.5)) - 0.5) * 24.0 for p in pitch_pts], dtype=np.float32)
                xs = np.clip(xs, 0.0, 1.0)
                ys = np.clip(ys, -12.0, 12.0)
                if 'sample_positions' not in locals():
                    sample_positions = np.linspace(0.0, 1.0, num=total_frames, dtype=np.float32)
                semitone_curve = np.interp(sample_positions, xs, ys).astype(np.float32)
                # Convert semitones to playback rate: 2^(semitones/12)
                rate_curve = np.power(2.0, semitone_curve / 12.0).astype(np.float32)
                # Build warped read positions (varispeed time map)
                # Use cumulative trapezoid starting at 0 for smooth phase
                phase = np.empty(total_frames, dtype=np.float64)
                phase[0] = 0.0
                np.cumsum(rate_curve[:-1], out=phase[1:])
                phase = phase / max(1e-6, phase[-1]) * float(total_frames - 1)  # normalize
                phase = np.clip(phase, 0.0, float(total_frames - 1))
                # Linear interpolation from source
                idx_low = np.floor(phase).astype(np.int64)
                idx_high = np.minimum(idx_low + 1, total_frames - 1)
                frac = (phase - idx_low.astype(np.float64)).astype(np.float32)
                src = data.copy()  # read from copy, write to original
                data[:, 0] = src[idx_low, 0] * (1.0 - frac) + src[idx_high, 0] * frac
                data[:, 1] = src[idx_low, 1] * (1.0 - frac) + src[idx_high, 1] * frac

            # Pitch automation (resample-based pitch shifting)
            pitch_pts = clip_auto.get("pitch", [])
            if pitch_pts and len(pitch_pts) >= 1:
                try:
                    xs = np.array([float(p.get("beat", 0)) / max(1e-6, clip_len_beats) for p in pitch_pts], dtype=np.float64)
                    # Map 0..1 normalized to semitones: 0.0=-24st, 0.5=0st, 1.0=+24st
                    ys = np.array([(float(p.get("value", 0.5)) - 0.5) * 48.0 for p in pitch_pts], dtype=np.float64)
                    xs = np.clip(xs, 0.0, 1.0)
                    ys = np.clip(ys, -24.0, 24.0)
                    sample_positions = np.linspace(0.0, 1.0, num=total_frames, dtype=np.float64)
                    semitone_curve = np.interp(sample_positions, xs, ys)
                    # Convert semitones to playback rate: rate = 2^(semitones/12)
                    rate_curve = np.power(2.0, semitone_curve / 12.0)
                    # Cumulative phase: where in the source to read for each output sample
                    cum_phase = np.cumsum(rate_curve)
                    # Normalize so it maps to source indices
                    src_indices = cum_phase - rate_curve[0]  # start at 0
                    src_max = float(total_frames - 1)
                    # Clamp to valid range
                    src_indices = np.clip(src_indices, 0.0, src_max)
                    # Linear interpolation resample
                    idx_floor = np.floor(src_indices).astype(np.int64)
                    idx_ceil = np.minimum(idx_floor + 1, total_frames - 1)
                    frac = (src_indices - idx_floor).astype(np.float32)
                    frac2 = frac[:, np.newaxis]  # shape (N, 1) for broadcasting
                    resampled = data[idx_floor] * (1.0 - frac2) + data[idx_ceil] * frac2
                    # Trim or pad to original length
                    if resampled.shape[0] >= total_frames:
                        data[:] = resampled[:total_frames]
                    else:
                        data[:resampled.shape[0]] = resampled
                        data[resampled.shape[0]:] = 0.0
                except Exception:
                    pass  # Pitch automation failed, keep original data

        # Clip-level gain/pan (optional). Track gain/pan is applied in audio callback (TrackParamState).
        clip_vol = float(getattr(clip, "volume", getattr(clip, "gain", 1.0)) or 1.0)
        clip_pan = float(getattr(clip, "pan", 0.0) or 0.0)
        gain_l, gain_r = _pan_gains(clip_vol, clip_pan)

        prepared.append(
            PreparedClip(
                start_sample=int(start_sample),
                end_sample=int(end_sample),
                offset_sample=int(offset_sample),
                data=data,
                gain_l=float(gain_l),
                gain_r=float(gain_r),
                track_idx=int(track_idx),
            )
        )

    prepared.sort(key=lambda c: c.start_sample)
    midi_events.sort(key=lambda e: (e.sample_pos, 0 if not e.is_note_on else 1))  # note_off before note_on at same pos
    return prepared, midi_events, bpm


class ArrangementState:
    """Realtime-safe-ish state holder for rendering.

    v0.0.20.25: Per-track rendering support (render_track + track clip map).
    The audio thread can render each track separately, apply TrackParamState
    (vol/pan/mute/solo) and update per-track meters without locks.

    Important design note:
    - render_track() does NOT advance the playhead.
    - advance() advances the playhead ONCE per block (call after mixing).
    """

    def __init__(self, prepared: List[PreparedClip], sr: int, start_beat: float, bpm: float,
                 loop_enabled: bool, loop_start_beat: float, loop_end_beat: float,
                 midi_events: Optional[List[PreparedMidiEvent]] = None):
        self.prepared = prepared
        self.sr = int(sr)
        self.bpm = float(bpm)
        self.beats_per_second = self.bpm / 60.0
        self.samples_per_beat = self.sr / max(1e-9, self.beats_per_second)
        self.playhead = int(round(float(start_beat) * self.samples_per_beat))

        self.loop_enabled = bool(loop_enabled)
        self.loop_start = int(round(float(loop_start_beat) * self.samples_per_beat))
        self.loop_end = int(round(float(loop_end_beat) * self.samples_per_beat))
        if self.loop_enabled:
            if self.loop_end <= self.loop_start:
                self.loop_enabled = False
            elif self.playhead < self.loop_start or self.playhead >= self.loop_end:
                self.playhead = self.loop_start

        # v0.0.20.42: Real-time MIDI events for sampler instrument tracks
        self._midi_events: List[PreparedMidiEvent] = sorted(
            midi_events or [], key=lambda e: (e.sample_pos, 0 if not e.is_note_on else 1)
        )
        self._midi_cursor: int = 0  # scan cursor (advances with playhead)

        # Per-track clip map (sorted by start_sample)
        self._track_clips: Dict[int, List[PreparedClip]] = {}
        self._track_indices: List[int] = []
        # Per-track scan positions to avoid O(N) scans in RT path
        self._track_pos: Dict[int, int] = {}
        self._last_playhead: int = int(self.playhead)

        self._build_track_map()

    def _build_track_map(self) -> None:
        self._track_clips.clear()
        for c in (self.prepared or []):
            try:
                tidx = int(getattr(c, "track_idx", 0))
            except Exception:
                tidx = 0
            self._track_clips.setdefault(tidx, []).append(c)

        for tidx, clips in self._track_clips.items():
            clips.sort(key=lambda cc: int(cc.start_sample))
            self._track_pos[tidx] = 0

        self._track_indices = sorted(self._track_clips.keys())

    def _reset_track_positions(self) -> None:
        for tidx in list(self._track_pos.keys()):
            self._track_pos[tidx] = 0
        self._midi_cursor = 0  # reset MIDI event cursor on loop

    def get_pending_midi_events(self, frames: int) -> List[PreparedMidiEvent]:
        """Return MIDI events in the current block [playhead, playhead+frames).

        v0.0.20.42: Used by the audio callback to trigger sampler note_on/note_off.
        """
        if not self._midi_events:
            return []

        start = int(self.playhead)
        end = int(start + int(frames))
        result: List[PreparedMidiEvent] = []

        # Advance cursor past events before current block
        while self._midi_cursor < len(self._midi_events):
            ev = self._midi_events[self._midi_cursor]
            if ev.sample_pos >= start:
                break
            self._midi_cursor += 1

        # Collect events in this block
        i = self._midi_cursor
        while i < len(self._midi_events):
            ev = self._midi_events[i]
            if ev.sample_pos >= end:
                break
            result.append(ev)
            i += 1

        return result

    def get_active_tracks(self, frames: int, out: Optional[List[int]] = None) -> List[int]:
        """Fill and return a list of track indices with clips overlapping this block."""
        if out is None:
            out = []
        else:
            out.clear()

        if not self._track_indices:
            return out

        start = int(self.playhead)
        end = int(start + int(frames))

        for tidx in self._track_indices:
            clips = self._track_clips.get(tidx)
            if not clips:
                continue

            i = int(self._track_pos.get(tidx, 0))
            # Advance cursor past clips that ended before this block
            while i < len(clips) and int(clips[i].end_sample) <= start:
                i += 1
            self._track_pos[tidx] = i

            if i < len(clips):
                c = clips[i]
                # If next clip starts before block end, it overlaps the block
                if int(c.start_sample) < end and int(c.end_sample) > start:
                    out.append(tidx)

        return out

    def render_track(self, track_idx: int, frames: int,
                     out: Optional["np.ndarray"] = None) -> "np.ndarray":
        """Render a single track into `out` (frames x 2). Does NOT advance playhead."""
        if np is None:
            raise RuntimeError("numpy fehlt")
        frames = int(frames)

        if out is None:
            out = np.zeros((frames, 2), dtype=np.float32)
        else:
            out = out[:frames]
            out.fill(0.0)

        clips = self._track_clips.get(int(track_idx))
        if not clips:
            return out

        start = int(self.playhead)
        end = int(start + frames)

        # Cursor optimization
        i = int(self._track_pos.get(int(track_idx), 0))
        while i < len(clips) and int(clips[i].end_sample) <= start:
            i += 1
        self._track_pos[int(track_idx)] = i

        for c in clips[i:]:
            if int(c.start_sample) >= end:
                break
            if int(c.end_sample) <= start:
                continue

            o_start = max(start, int(c.start_sample))
            o_end = min(end, int(c.end_sample))
            n = int(o_end - o_start)
            if n <= 0:
                continue

            out_off = int(o_start - start)
            rel = int(o_start - int(c.start_sample))
            src_start = int(int(c.offset_sample) + rel)
            src_end = int(src_start + n)

            if src_start >= int(c.data.shape[0]):
                continue
            if src_end > int(c.data.shape[0]):
                src_end = int(c.data.shape[0])
                n = int(src_end - src_start)
            if n <= 0:
                continue

            chunk = c.data[src_start:src_end]
            # Clip-level gain (track-level gain is applied later in the audio callback)
            out[out_off:out_off + n, 0] += chunk[:, 0] * float(c.gain_l)
            out[out_off:out_off + n, 1] += chunk[:, 1] * float(c.gain_r)

        return out

    def advance(self, frames: int) -> None:
        """Advance playhead by `frames` with loop handling. Call ONCE per block."""
        frames = int(frames)
        prev = int(self.playhead)

        next_ph = int(prev + frames)
        if self.loop_enabled and next_ph >= self.loop_end:
            overflow = int(next_ph - self.loop_end)
            span = max(1, int(self.loop_end - self.loop_start))
            overflow = int(overflow % span)
            next_ph = int(self.loop_start + overflow)

        self.playhead = int(next_ph)

        # If playhead jumped backwards (loop wrap), reset cursors.
        if int(self.playhead) < prev:
            self._reset_track_positions()

        self._last_playhead = int(self.playhead)

    def render(self, frames: int) -> "np.ndarray":
        """Backward-compatible full-mix render (allocates). Advances playhead."""
        if np is None:
            raise RuntimeError("numpy fehlt")
        frames = int(frames)
        out = np.zeros((frames, 2), dtype=np.float32)

        # Mix all tracks (clip-level gains only)
        tracks = self.get_active_tracks(frames)
        if tracks:
            tmp = np.zeros((frames, 2), dtype=np.float32)
            for tidx in tracks:
                self.render_track(int(tidx), frames, out=tmp)
                out[:frames] += tmp[:frames]

        out = np.clip(out, -1.0, 1.0)
        self.advance(frames)
        return out

