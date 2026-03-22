"""MIDI import/export (v0.0.3).

Uses 'mido' for robust reading/writing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

class MidiIOError(RuntimeError):
    pass


def import_midi(path: Path) -> Dict[str, Any]:
    """Parse a MIDI file and return a minimal neutral representation."""
    try:
        import mido  # type: ignore
    except Exception as exc:
        raise MidiIOError("mido ist nicht installiert. Bitte requirements installieren.") from exc

    mid = mido.MidiFile(str(path))
    tracks: List[Dict[str, Any]] = []
    for ti, t in enumerate(mid.tracks):
        events = []
        abs_time = 0
        for msg in t:
            abs_time += msg.time
            events.append({"time": abs_time, "msg": msg.dict()})
        tracks.append({"name": getattr(t, "name", f"Track {ti}"), "events": events})
    return {"ticks_per_beat": mid.ticks_per_beat, "tracks": tracks}


def export_midi(data: Dict[str, Any], out_path: Path) -> Path:
    try:
        import mido  # type: ignore
    except Exception as exc:
        raise MidiIOError("mido ist nicht installiert. Bitte requirements installieren.") from exc

    ticks_per_beat = int(data.get("ticks_per_beat", 480))
    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    for t in data.get("tracks", []):
        mt = mido.MidiTrack()
        mid.tracks.append(mt)
        last_time = 0
        for e in t.get("events", []):
            abs_time = int(e.get("time", 0))
            delta = max(0, abs_time - last_time)
            last_time = abs_time
            msg_dict = dict(e.get("msg", {}))
            msg_dict["time"] = delta
            mt.append(mido.Message.from_dict(msg_dict))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mid.save(str(out_path))
    return out_path
