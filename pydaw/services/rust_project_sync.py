# -*- coding: utf-8 -*-
"""Rust Project Sync — Serialize Python Project → Rust ProjectSync JSON.

v0.0.20.707 — Phase RA1

Converts the Python Project model into the JSON format expected by the
Rust engine's ``audio_bridge::ProjectSync`` struct and sends it via
the ``RustEngineBridge``.

The Rust engine receives the full project state in one IPC message
(Command::SyncProject) and rebuilds its internal AudioGraph from it.

Usage:
    from pydaw.services.rust_project_sync import RustProjectSyncer

    syncer = RustProjectSyncer(bridge, project_service)
    syncer.sync()              # full project sync
    syncer.on_play()           # sync + Play
    syncer.on_stop()           # Stop
    syncer.on_seek(beat=8.0)   # Seek

JSON format matches Rust ``audio_bridge::ProjectSync``:
    {
      "bpm": 120.0,
      "time_sig_num": 4, "time_sig_den": 4,
      "loop_enabled": false, "loop_start_beat": 0.0, "loop_end_beat": 16.0,
      "sample_rate": 48000, "sync_seq": 1,
      "tracks": [{"track_id": "trk_...", "track_index": 0, "kind": "audio",
                   "volume": 0.8, "pan": 0.0, "muted": false, "soloed": false,
                   "instrument_type": null, "instrument_id": null,
                   "group_index": null}],
      "clips": [{"clip_id": "clip_...", "track_id": "trk_...",
                  "start_beats": 0.0, "length_beats": 4.0, "kind": "midi",
                  "audio_b64": null, "source_sr": null, "source_channels": null,
                  "gain": 1.0, "offset_beats": 0.0}],
      "midi_notes": [{"clip_id": "clip_...", "pitch": 60, "velocity": 100,
                       "start_beats": 0.0, "length_beats": 1.0}],
      "automation": [{"track_id": "trk_...", "param_id": "volume",
                       "points": [{"beat": 0.0, "value": 0.8, "curve": "linear"}]}]
    }
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serializer: Python Project → Rust ProjectSync dict
# ---------------------------------------------------------------------------

def serialize_project_sync(project: Any, sync_seq: int = 1) -> dict:
    """Convert a Project model instance to a Rust-compatible ProjectSync dict.

    Args:
        project: pydaw.model.project.Project instance
        sync_seq: Sequence number for delta detection (incrementing)

    Returns:
        dict matching Rust audio_bridge::ProjectSync
    """
    # --- Transport ---
    bpm = float(getattr(project, "bpm", 120.0) or 120.0)
    ts = str(getattr(project, "time_signature", "4/4") or "4/4")
    ts_parts = ts.split("/")
    ts_num = int(ts_parts[0]) if len(ts_parts) >= 1 else 4
    ts_den = int(ts_parts[1]) if len(ts_parts) >= 2 else 4
    sr = int(getattr(project, "sample_rate", 48000) or 48000)

    # Loop region
    loop_enabled = False
    loop_start = 0.0
    loop_end = 16.0
    try:
        # Check if transport has loop info
        loop_enabled = bool(getattr(project, "loop_enabled", False))
        loop_start = float(getattr(project, "loop_start_beat", 0.0) or 0.0)
        loop_end = float(getattr(project, "loop_end_beat", 16.0) or 16.0)
    except Exception:
        pass

    # --- Tracks ---
    tracks_list: List[dict] = []
    track_id_to_index: Dict[str, int] = {}
    master_index: Optional[int] = None

    all_tracks = list(getattr(project, "tracks", []) or [])

    # First pass: assign indices and find master
    for i, trk in enumerate(all_tracks):
        tid = str(getattr(trk, "id", "") or "")
        track_id_to_index[tid] = i
        kind = str(getattr(trk, "kind", "audio") or "audio")
        if kind == "master":
            master_index = i

    # Second pass: build TrackConfig list
    for i, trk in enumerate(all_tracks):
        tid = str(getattr(trk, "id", "") or "")
        kind = str(getattr(trk, "kind", "audio") or "audio")

        # Map kind names
        kind_map = {
            "audio": "audio",
            "instrument": "instrument",
            "bus": "group",
            "group": "group",
            "master": "master",
            "fx": "fx_return",
        }
        rust_kind = kind_map.get(kind, "audio")

        # Instrument info
        inst_type = None
        inst_id = None
        if kind == "instrument" or getattr(trk, "plugin_type", None):
            pt = str(getattr(trk, "plugin_type", "") or "")
            if pt:
                inst_type = pt
                inst_id = f"{tid}:{pt}"

        # Group routing
        group_idx = None
        out_target = str(getattr(trk, "output_target_id", "") or "")
        if out_target and out_target in track_id_to_index:
            group_idx = track_id_to_index[out_target]
        # If not explicitly routed and not master → route to master
        if group_idx is None and kind != "master" and master_index is not None:
            group_idx = master_index

        tc = {
            "track_id": tid,
            "track_index": i,
            "kind": rust_kind,
            "volume": float(getattr(trk, "volume", 0.8) or 0.8),
            "pan": float(getattr(trk, "pan", 0.0) or 0.0),
            "muted": bool(getattr(trk, "muted", False)),
            "soloed": bool(getattr(trk, "solo", False)),
            "instrument_type": inst_type,
            "instrument_id": inst_id,
            "group_index": group_idx,
        }
        tracks_list.append(tc)

    # --- Clips ---
    clips_list: List[dict] = []
    all_clips = list(getattr(project, "clips", []) or [])

    for clip in all_clips:
        # Skip launcher-only clips
        if getattr(clip, "launcher_only", False):
            continue
        # Skip muted clips
        if getattr(clip, "muted", False):
            continue

        cid = str(getattr(clip, "id", "") or "")
        kind = str(getattr(clip, "kind", "audio") or "audio")
        tid = str(getattr(clip, "track_id", "") or "")

        cc = {
            "clip_id": cid,
            "track_id": tid,
            "start_beats": float(getattr(clip, "start_beats", 0.0) or 0.0),
            "length_beats": float(getattr(clip, "length_beats", 4.0) or 4.0),
            "kind": kind,
            "audio_b64": None,      # Audio data sent separately in RA2
            "source_sr": None,
            "source_channels": None,
            "gain": float(getattr(clip, "gain", 1.0) or 1.0),
            "offset_beats": float(getattr(clip, "offset_beats", 0.0) or 0.0),
        }
        clips_list.append(cc)

    # --- MIDI Notes ---
    notes_list: List[dict] = []
    midi_notes_dict = dict(getattr(project, "midi_notes", {}) or {})

    for clip_id, notes in midi_notes_dict.items():
        if not isinstance(notes, (list, tuple)):
            continue
        for note in notes:
            try:
                nc = {
                    "clip_id": str(clip_id),
                    "pitch": int(getattr(note, "pitch", 60) or 60),
                    "velocity": int(getattr(note, "velocity", 100) or 100),
                    "start_beats": float(getattr(note, "start", 0.0) or 0.0),
                    "length_beats": float(getattr(note, "length", 1.0) or 1.0),
                }
                notes_list.append(nc)
            except Exception:
                continue

    # --- Automation ---
    auto_list: List[dict] = []
    auto_lanes = dict(getattr(project, "automation_manager_lanes", {}) or {})

    for param_key, lane_data in auto_lanes.items():
        if not isinstance(lane_data, dict):
            continue

        track_id = str(lane_data.get("track_id", "") or "")
        param_id = str(lane_data.get("parameter_id", param_key) or param_key)
        breakpoints = lane_data.get("breakpoints", [])

        if not track_id or not breakpoints:
            continue

        points: List[dict] = []
        for bp in breakpoints:
            if not isinstance(bp, dict):
                continue
            try:
                pt = {
                    "beat": float(bp.get("beat", 0.0) or 0.0),
                    "value": float(bp.get("value", 0.0) or 0.0),
                    "curve": str(bp.get("curve_type", "linear") or "linear"),
                }
                points.append(pt)
            except Exception:
                continue

        if points:
            auto_list.append({
                "track_id": track_id,
                "param_id": param_id,
                "points": points,
            })

    # --- Assemble ProjectSync ---
    return {
        "bpm": bpm,
        "time_sig_num": ts_num,
        "time_sig_den": ts_den,
        "loop_enabled": loop_enabled,
        "loop_start_beat": loop_start,
        "loop_end_beat": loop_end,
        "sample_rate": sr,
        "sync_seq": sync_seq,
        "tracks": tracks_list,
        "clips": clips_list,
        "midi_notes": notes_list,
        "automation": auto_list,
    }


# ---------------------------------------------------------------------------
# Syncer: Orchestrates project sync + transport commands
# ---------------------------------------------------------------------------

class RustProjectSyncer:
    """Orchestrates full project sync + transport for the Rust engine.

    Holds a reference to the bridge and project service. On play(),
    it serializes the full project and sends it as one SyncProject
    command, then sends Play.

    Usage:
        syncer = RustProjectSyncer(bridge, project_service)
        syncer.on_play()   # serialize → SyncProject → Play
        syncer.on_stop()   # Stop
        syncer.on_seek(8)  # Seek to beat 8
    """

    def __init__(self, bridge: Any, project_service: Any):
        self._bridge = bridge
        self._project_svc = project_service
        self._sync_seq = 0
        self._sample_syncer = None  # lazy init

    def _get_sample_syncer(self):
        """Lazy-init the RustSampleSyncer (RA2)."""
        if self._sample_syncer is None:
            try:
                from pydaw.services.rust_sample_sync import RustSampleSyncer
                self._sample_syncer = RustSampleSyncer(
                    self._bridge, self._project_svc)
            except ImportError:
                _log.debug("rust_sample_sync not available")
        return self._sample_syncer

    @property
    def _project(self):
        """Get the current Project instance."""
        try:
            ctx = getattr(self._project_svc, "ctx", None)
            if ctx:
                return getattr(ctx, "project", None)
        except Exception:
            pass
        return None

    def sync(self) -> bool:
        """Send full project state to Rust engine.

        Returns True if sent successfully.
        """
        project = self._project
        if project is None:
            _log.warning("RustProjectSyncer.sync(): no project loaded")
            return False

        bridge = self._bridge
        if bridge is None or not getattr(bridge, "_connected", False):
            _log.debug("RustProjectSyncer.sync(): bridge not connected")
            return False

        self._sync_seq += 1
        try:
            sync_dict = serialize_project_sync(project, self._sync_seq)
            project_json = json.dumps(sync_dict, separators=(",", ":"))

            ok = bridge.send_command({
                "cmd": "SyncProject",
                "project_json": project_json,
            })

            if ok:
                _log.info(
                    "SyncProject sent: seq=%d, %d tracks, %d clips, %d notes, %d auto",
                    self._sync_seq,
                    len(sync_dict.get("tracks", [])),
                    len(sync_dict.get("clips", [])),
                    len(sync_dict.get("midi_notes", [])),
                    len(sync_dict.get("automation", [])),
                )
            else:
                _log.warning("SyncProject send failed")
            return ok

        except Exception as e:
            _log.error("SyncProject serialization error: %s", e)
            return False

    def on_play(self) -> bool:
        """Sync project state + audio samples, then start playback.

        Ensures Rust engine has the latest project data and audio clips
        before playing. Sequence: SyncProject → LoadAudioClips → Play.
        """
        ok = self.sync()
        if ok:
            # RA2: Send audio sample data
            try:
                ss = self._get_sample_syncer()
                if ss is not None:
                    count = ss.sync_all()
                    _log.info("Sample sync: %d clips sent", count)
            except Exception as e:
                _log.warning("Sample sync failed (non-fatal): %s", e)

            try:
                self._bridge.play()
            except Exception as e:
                _log.error("play() failed: %s", e)
                return False
        return ok

    def on_stop(self) -> None:
        """Stop playback on Rust engine."""
        try:
            if self._bridge and getattr(self._bridge, "_connected", False):
                self._bridge.stop()
        except Exception as e:
            _log.error("stop() failed: %s", e)

    def on_seek(self, beat: float) -> None:
        """Seek to a beat position on Rust engine."""
        try:
            if self._bridge and getattr(self._bridge, "_connected", False):
                self._bridge.seek(float(beat))
        except Exception as e:
            _log.error("seek() failed: %s", e)

    def on_tempo_changed(self, bpm: float) -> None:
        """Notify Rust engine of tempo change."""
        try:
            if self._bridge and getattr(self._bridge, "_connected", False):
                self._bridge.set_tempo(float(bpm))
        except Exception as e:
            _log.error("set_tempo() failed: %s", e)

    def on_loop_changed(self, enabled: bool, start: float, end: float) -> None:
        """Notify Rust engine of loop region change."""
        try:
            if self._bridge and getattr(self._bridge, "_connected", False):
                self._bridge.set_loop(enabled, start, end)
        except Exception as e:
            _log.error("set_loop() failed: %s", e)

    def on_track_param_changed(self, track_index: int, param: str,
                                value: float) -> None:
        """Notify Rust engine of a track parameter change (Volume/Pan/Mute/Solo)."""
        try:
            if self._bridge and getattr(self._bridge, "_connected", False):
                self._bridge.set_track_param(track_index, param, value)
        except Exception as e:
            _log.error("set_track_param() failed: %s", e)
