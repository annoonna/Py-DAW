"""Shared SmartDrop target evaluation helpers.

Safety-first helper for Arranger Canvas + TrackList so both surfaces show the
same SmartDrop language and can explain blocked Instrument->Audio targets
without mutating project state.
"""

from __future__ import annotations

from typing import Any

from pydaw.services.smartdrop_morph_guard import build_audio_to_instrument_morph_plan


def _count_chain_devices(chain: Any) -> int:
    try:
        devices = (chain or {}).get("devices", []) if isinstance(chain, dict) else []
        return len([d for d in list(devices or []) if d is not None])
    except Exception:
        return 0


def _collect_track_clip_counts(project_obj: Any, track_id: str) -> tuple[int, int]:
    audio_count = 0
    midi_count = 0
    if not project_obj or not track_id:
        return audio_count, midi_count
    try:
        for clip in list(getattr(project_obj, "clips", []) or []):
            if str(getattr(clip, "track_id", "") or "") != str(track_id):
                continue
            kind = str(getattr(clip, "kind", "") or "").strip().lower()
            if kind == "audio":
                audio_count += 1
            elif kind == "midi":
                midi_count += 1
    except Exception:
        return 0, 0
    return audio_count, midi_count


def _plural(value: int, singular: str, plural: str | None = None) -> str:
    plural = plural or f"{singular}s"
    return f"{value} {singular if int(value) == 1 else plural}"


def _track_kind_label(track_kind: str) -> str:
    track_kind = str(track_kind or "").strip().lower()
    return {
        "audio": "Audio-Spur",
        "instrument": "Instrument-Spur",
        "bus": "Bus-Spur",
        "fx": "FX-Spur",
        "group": "Gruppen-Spur",
        "master": "Master-Spur",
    }.get(track_kind, "Spur")


def evaluate_plugin_drop_target(project_obj: Any, track: Any, device_kind: str) -> dict[str, Any]:
    """Return a shared, UI-safe SmartDrop decision for one target track.

    Keys:
      - label: short UI label for hover preview
      - actionable: whether a real SmartDrop is already allowed
      - blocked_message: optional status text when user drops on a blocked target
      - target_kind: normalized track kind
      - audio_clip_count / midi_clip_count / note_fx_count / audio_fx_count
    """
    try:
        track_name = str(getattr(track, "name", "") or getattr(track, "id", "") or "Spur")
        track_id = str(getattr(track, "id", "") or "")
        track_kind = str(getattr(track, "kind", "") or "").strip().lower()
        device_kind = str(device_kind or "").strip().lower()
        note_fx_count = _count_chain_devices(getattr(track, "note_fx_chain", {}) or {})
        audio_fx_count = _count_chain_devices(getattr(track, "audio_fx_chain", {}) or {})
        audio_clip_count, midi_clip_count = _collect_track_clip_counts(project_obj, track_id)

        info = {
            "label": "",
            "actionable": False,
            "blocked_message": "",
            "target_kind": track_kind,
            "audio_clip_count": int(audio_clip_count),
            "midi_clip_count": int(midi_clip_count),
            "note_fx_count": int(note_fx_count),
            "audio_fx_count": int(audio_fx_count),
        }

        if device_kind == "instrument":
            if track_kind == "instrument":
                info["label"] = f"Instrument → Einfügen auf {track_name}"
                info["actionable"] = True
                return info
            if track_kind == "audio":
                plan = dict(build_audio_to_instrument_morph_plan(project_obj, track) or {})
                info["label"] = str(plan.get("preview_label") or f"Instrument → Preview auf {track_name} · Audio-Spur")
                info["blocked_message"] = str(plan.get("blocked_message") or "")
                info["audio_clip_count"] = int(plan.get("audio_clip_count", audio_clip_count) or 0)
                info["midi_clip_count"] = int(plan.get("midi_clip_count", midi_clip_count) or 0)
                info["note_fx_count"] = int(plan.get("note_fx_count", note_fx_count) or 0)
                info["audio_fx_count"] = int(plan.get("audio_fx_count", audio_fx_count) or 0)
                return info
            info["label"] = f"Instrument → Preview auf {track_name} · {_track_kind_label(track_kind)}"
            info["blocked_message"] = (
                f"SmartDrop noch gesperrt: Instrumente können aktuell nicht direkt auf {_track_kind_label(track_kind)} gelegt werden."
            )
            return info

        if device_kind == "note_fx":
            if track_kind == "instrument":
                info["label"] = f"Note-FX → Einfügen auf {track_name}"
                info["actionable"] = True
            else:
                info["label"] = f"Note-FX → Preview auf {track_name} · {_track_kind_label(track_kind)}"
            return info

        if track_kind in ("instrument", "audio", "bus", "group", "fx"):
            info["label"] = f"Effekt → Einfügen auf {track_name}"
            info["actionable"] = True
        else:
            info["label"] = f"Effekt → Preview auf {track_name} · {_track_kind_label(track_kind)}"
        return info
    except Exception:
        return {
            "label": "",
            "actionable": False,
            "blocked_message": "",
            "target_kind": "",
            "audio_clip_count": 0,
            "midi_clip_count": 0,
            "note_fx_count": 0,
            "audio_fx_count": 0,
        }
