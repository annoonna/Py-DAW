
"""MIDI clip rendering to audio via FluidSynth (Phase 4).

Design goal:
- Provide a pragmatic, reliable way to HEAR instrument tracks (SF2) without
  implementing a full realtime synth graph yet.
- Render MIDI notes for a given clip into a temporary WAV file using the
  system's `fluidsynth` binary, then let the audio engine mix the WAV like a
  normal audio clip.

This keeps the GUI responsive and works well with PipeWire/ALSA setups.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
import hashlib
import os
import subprocess
import tempfile
import json

from .note_expression_eval import effective_velocity, should_play_note, cc74_value, pressure_value, effective_micropitch, effective_micropitch_note_start, micropitch_curve_points


try:
    import mido
except Exception:  # pragma: no cover
    mido = None



def midi_content_hash(
    *,
    notes: Optional[List[Dict[str, Any]]],
    bpm: float,
    clip_length_beats: float,
    sf2_bank: int,
    sf2_preset: int,
) -> str:
    """Return a stable content hash for a MIDI clip.

    IMPORTANT:
    - Notes may be dicts OR MidiNote-like objects.
    - We hash start/length in beats, pitch, velocity AND expression payload.
      Otherwise expression edits (velocity/chance/...) would NOT invalidate the
      render cache and the user would hear no change.
    """

    h = hashlib.sha1()
    h.update(f"bpm={float(bpm):.9f};len={float(clip_length_beats):.9f};".encode("utf-8"))
    h.update(f"bank={int(sf2_bank)};preset={int(sf2_preset)};".encode("utf-8"))
    # Render-format tag: invalidate stale cache files when MIDI->SF2 rendering
    # semantics change (e.g. MPE/micropitch channel program init).
    h.update(b"renderfmt:sf2-allch-program-v1;")

    # Include playback mapping toggles into the hash so switching them forces a re-render.
    try:
        from pydaw.core.settings_store import get_settings  # type: ignore
        _qs = get_settings()
        def _qbool(v: object, default: bool = True) -> bool:
            if isinstance(v, bool):
                return v
            if v is None:
                return default
            s = str(v).strip().lower()
            if s in ("1", "true", "yes", "on"):
                return True
            if s in ("0", "false", "no", "off"):
                return False
            return default
        _apply_vel = _qbool(_qs.value("audio/note_expr_apply_velocity", True), True)
        _apply_chance = _qbool(_qs.value("audio/note_expr_apply_chance", True), True)
        _cc74 = _qbool(_qs.value("audio/note_expr_send_cc74", True), True)
        _press = _qbool(_qs.value("audio/note_expr_send_pressure", True), True)
        _mpe = _qbool(_qs.value("audio/note_expr_mpe_mode", False), False)
        h.update(f"expr:{int(_apply_vel)}{int(_apply_chance)}{int(_cc74)}{int(_press)}{int(_mpe)};".encode("utf-8"))
    except Exception:
        h.update(b"expr:default;")

    if not notes:
        h.update(b"notes:[]")
        return h.hexdigest()

    def _get(n: Any, key: str, default: Any):
        if isinstance(n, dict):
            return n.get(key, default)
        return getattr(n, key, default)

    def _start(n: Any) -> float:
        return float(_get(n, "start_beats", _get(n, "start", 0.0)))

    def _length(n: Any) -> float:
        return float(_get(n, "length_beats", _get(n, "length", 0.0)))

    def _key(n: Any):
        return (
            _start(n),
            _length(n),
            int(_get(n, "pitch", 0)),
            int(_get(n, "velocity", 0)),
        )

    include_params = ("velocity", "chance", "timbre", "pressure", "micropitch")

    for n in sorted(notes, key=_key):
        try:
            start = _start(n)
            length = _length(n)
            pitch = int(_get(n, "pitch", 0))
            vel = int(_get(n, "velocity", 0))
        except Exception:
            continue
        h.update(f"{start:.9f},{length:.9f},{pitch},{vel};".encode("utf-8"))

        expr = _get(n, "expressions", None)
        if isinstance(expr, dict):
            filtered = {k: expr.get(k) for k in include_params if k in expr}
            try:
                h.update(json.dumps(filtered, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            except Exception:
                pass

    return h.hexdigest()

@dataclass(frozen=True)
class RenderKey:
    clip_id: str
    sf2_path: str
    sf2_bank: int
    sf2_preset: int
    bpm: float
    samplerate: int
    clip_length_beats: float
    content_hash: str


def _cache_dir() -> Path:
    # User-level cache; safe across projects
    d = Path(os.path.expanduser("~")) / ".cache" / "Py_DAW"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _key_to_filename(key: RenderKey) -> str:
    h = hashlib.sha1(
        f"{key.clip_id}|{key.sf2_path}|{key.sf2_bank}|{key.sf2_preset}|{key.bpm}|{key.samplerate}|{key.clip_length_beats}|{key.content_hash}".encode(
            "utf-8"
        )
    ).hexdigest()[:16]
    return f"midi_{key.clip_id}_{h}.wav"


def ensure_rendered_wav(
    *,
    key: RenderKey,
    midi_notes: List[Any],
    clip_start_beats: float,
    clip_length_beats: float,
) -> Optional[Path]:
    """Render notes into a WAV file and return the path, or None on failure.

    `midi_notes` is expected to contain objects with attributes:
    - pitch (int)
    - start_beats (float)
    - length_beats (float)
    - velocity (int, optional)
    """
    if mido is None:
        return None

    sf2 = Path(key.sf2_path)
    if not sf2.exists():
        return None

    out = _cache_dir() / _key_to_filename(key)
    if out.exists() and out.stat().st_size > 44:
        return out

    # Build a tiny Standard MIDI file for the clip region.
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)

    # Tempo meta (microseconds per beat)
    tempo = mido.bpm2tempo(float(key.bpm))
    track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))

    # Program change: bank/preset
    # IMPORTANT:
    # - In MPE mode, micropitch notes are moved onto channels 1..15 so each
    #   note can have its own pitchwheel stream.
    # - Therefore the target SF2 bank/preset MUST be selected on *all* usable
    #   channels, not only channel 0. Otherwise MPE-routed notes may play with
    #   the wrong default patch (or appear to ignore micropitch on the intended
    #   instrument).
    # - Safe choice: initialize all 16 channels with the same bank/preset.
    ch = 0
    for _ch in range(16):
        track.append(mido.Message("control_change", channel=int(_ch), control=0, value=int(key.sf2_bank) & 0x7F, time=0))
        track.append(mido.Message("program_change", channel=int(_ch), program=int(key.sf2_preset) & 0x7F, time=0))


    # Playback mapping toggles (optional, QSettings).
    # Defaults are safe because we only emit extra events when expressions exist.
    send_cc74 = True
    send_pressure = True
    apply_velocity_expr = True
    apply_chance_expr = True
    mpe_mode = False

    def _qbool(v: object, default: bool = True) -> bool:
        if isinstance(v, bool):
            return v
        if v is None:
            return default
        s = str(v).strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off"):
            return False
        return default

    try:
        from pydaw.core.settings_store import get_settings  # type: ignore
        _qs = get_settings()
        send_cc74 = _qbool(_qs.value("audio/note_expr_send_cc74", True), True)
        send_pressure = _qbool(_qs.value("audio/note_expr_send_pressure", True), True)
        apply_velocity_expr = _qbool(_qs.value("audio/note_expr_apply_velocity", True), True)
        apply_chance_expr = _qbool(_qs.value("audio/note_expr_apply_chance", True), True)
        mpe_mode = _qbool(_qs.value("audio/note_expr_mpe_mode", False), False)
    except Exception:
        pass


    # Convert beats -> ticks
    def beat_to_ticks(b: float) -> int:
        return int(round(b * 480))

    def _pitchwheel_from_semitones(semi: float, bend_range: float = 12.0) -> int:
        try:
            s2 = float(semi)
        except Exception:
            s2 = 0.0
        br = max(0.01, float(bend_range))
        s2 = max(-br, min(br, s2))
        val = int(round((s2 / br) * 8191.0))
        return max(-8192, min(8191, val))

    def _append_pitchbend_range_setup(channel: int, semitones: int = 12) -> None:
        events.append((0.0, -3, mido.Message("control_change", channel=int(channel), control=101, value=0, time=0)))
        events.append((0.0, -3, mido.Message("control_change", channel=int(channel), control=100, value=0, time=0)))
        events.append((0.0, -3, mido.Message("control_change", channel=int(channel), control=6, value=int(semitones) & 0x7F, time=0)))
        events.append((0.0, -3, mido.Message("control_change", channel=int(channel), control=38, value=0, time=0)))
        events.append((0.0, -3, mido.Message("control_change", channel=int(channel), control=101, value=127, time=0)))
        events.append((0.0, -3, mido.Message("control_change", channel=int(channel), control=100, value=127, time=0)))

    events: list[tuple[float, int, Any]] = []
    if mpe_mode:
        for _ch in range(1, 16):
            _append_pitchbend_range_setup(_ch, 12)

    # Notes are stored relative to clip start; we normalize into [0, clip_length]
    for n in midi_notes or []:
        try:
            pitch = int(getattr(n, "pitch"))
            start_b = float(getattr(n, "start_beats"))
            length_b = float(getattr(n, "length_beats"))
        except Exception:
            continue

        # clamp to clip range
        start_b = max(0.0, min(start_b, float(clip_length_beats)))
        end_b = max(0.0, min(start_b + max(0.0, length_b), float(clip_length_beats)))
        if end_b <= start_b:
            continue

        # Chance gate (deterministic)
        if apply_chance_expr and (not should_play_note(clip_id=str(key.clip_id), note=n, abs_start_beats=float(start_b))):
            continue

        # Note-on velocity (expression overrides base velocity)
        vel = int(effective_velocity(n)) if apply_velocity_expr else int(getattr(n, "velocity", 100) or 100)

        note_ch = ch
        micro = None
        if mpe_mode:
            try:
                micro = effective_micropitch_note_start(n)
            except Exception:
                micro = None
            if micro is not None:
                note_ch = 1 + (len(events) % 15)

        # Expression-driven MIDI at note start (safe: only if expression exists)
        cc74 = cc74_value(n)
        pr = pressure_value(n)

        if send_cc74 and (cc74 is not None):
            events.append((start_b, 1, mido.Message("control_change", channel=note_ch, control=74, value=int(cc74), time=0)))
        if send_pressure and (pr is not None):
            events.append((start_b, 1, mido.Message("polytouch", channel=note_ch, note=int(pitch), value=int(pr), time=0)))
        if mpe_mode and (micro is not None):
            events.append((start_b, 1, mido.Message("pitchwheel", channel=note_ch, pitch=_pitchwheel_from_semitones(float(micro), 12.0), time=0)))
            try:
                for tt, vv in micropitch_curve_points(n, steps=14):
                    beat_pos = float(start_b) + (float(end_b - start_b) * float(tt))
                    if beat_pos <= float(start_b) + 1e-6 or beat_pos >= float(end_b) - 1e-6:
                        continue
                    events.append((beat_pos, 1, mido.Message("pitchwheel", channel=note_ch, pitch=_pitchwheel_from_semitones(float(vv), 12.0), time=0)))
            except Exception:
                pass

        events.append((start_b, 2, mido.Message("note_on", channel=note_ch, note=int(pitch), velocity=int(vel), time=0)))
        events.append((end_b, 0, mido.Message("note_off", channel=note_ch, note=int(pitch), velocity=0, time=0)))
        if mpe_mode and (micro is not None):
            events.append((end_b, 1, mido.Message("pitchwheel", channel=note_ch, pitch=0, time=0)))

    # Sort by beat; order within same beat: note_off (0), cc/aftertouch (1), note_on (2)
    events.sort(key=lambda e: (float(e[0]), int(e[1])))

    last_tick = 0
    for beat, _prio, msg in events:
        tick = beat_to_ticks(float(beat))
        delta = max(0, tick - last_tick)
        last_tick = tick
        try:
            msg.time = int(delta)
        except Exception:
            pass
        track.append(msg)

    # End of track
    track.append(mido.MetaMessage("end_of_track", time=beat_to_ticks(float(clip_length_beats)) - last_tick))

    # Write midi to temp file
    tmp_mid = Path(tempfile.gettempdir()) / f"pydaw_{key.clip_id}.mid"
    try:
        mid.save(tmp_mid.as_posix())
    except Exception:
        return None

    # Render to wav via fluidsynth
    # fluidsynth -ni -r 48000 -F out.wav sf2.mid
    cmd = [
        "fluidsynth",
        "-ni",
        "-r",
        str(int(key.samplerate)),
        "-F",
        out.as_posix(),
        sf2.as_posix(),
        tmp_mid.as_posix(),
    ]
    try:
        # FIXED v0.0.19.7.14: TIMEOUT 30 Sekunden!
        result = subprocess.run(
            cmd, 
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, 
            check=False,  # Don't raise on error
            timeout=30  # 30 seconds max! ✅
        )
        
        if result.returncode != 0:
            # FluidSynth failed
            stderr_msg = result.stderr.decode('utf-8', errors='ignore')[:200] if result.stderr else "Unknown error"
            raise RuntimeError(f"FluidSynth failed: {stderr_msg}")
            
    except subprocess.TimeoutExpired:
        # FIXED v0.0.19.7.14: FluidSynth hängt!
        raise RuntimeError("FluidSynth timeout (30s) - clip may be too long or FluidSynth hung")
    except Exception as e:
        # leave no half file
        try:
            if out.exists():
                out.unlink()
        except Exception:
            pass
        raise  # Re-raise so caller knows it failed!

    return out if out.exists() and out.stat().st_size > 44 else None
