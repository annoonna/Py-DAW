# -*- coding: utf-8 -*-
"""Rust Sample Sync — Load audio samples and send to Rust engine.

v0.0.20.708 — Phase RA2

Scans the project for audio clips and instrument samples, loads them
from disk, converts to f32 interleaved PCM, and sends each one to the
Rust engine via LoadAudioClip IPC commands.

Also builds the SetArrangement placement list so the Rust engine knows
which clips play where on the timeline.

Usage:
    from pydaw.services.rust_sample_sync import RustSampleSyncer

    syncer = RustSampleSyncer(bridge, project_service)
    syncer.sync_all()             # send all audio data + arrangement
    syncer.sync_clip(clip_id)     # send one clip

Chunking:
    Files > MAX_CHUNK_BYTES (50 MB) are split into chunks to avoid
    IPC buffer overflows. Each chunk has a unique clip_id suffix.

Cache:
    A hash of (path, mtime, size) is kept per clip. Only changed clips
    are re-sent on subsequent sync_all() calls.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from typing import Any, Dict, List, Optional, Set, Tuple

_log = logging.getLogger(__name__)

# Max raw audio bytes before chunking (50 MB)
MAX_CHUNK_BYTES = 50 * 1024 * 1024

try:
    import numpy as np
    _NP = True
except ImportError:
    np = None  # type: ignore
    _NP = False


# ---------------------------------------------------------------------------
# Audio file loader
# ---------------------------------------------------------------------------

def _load_audio_file(path: str) -> Optional[Tuple[Any, int, int]]:
    """Load an audio file and return (f32_interleaved_numpy, channels, sr).

    Tries soundfile first, falls back to scipy.io.wavfile.
    Returns None on failure.
    """
    if not _NP:
        _log.warning("numpy not available — cannot load audio")
        return None

    if not path or not os.path.isfile(path):
        return None

    # Try soundfile
    try:
        import soundfile as sf
        data, sr = sf.read(path, dtype="float32", always_2d=True)
        # data shape: (frames, channels)
        channels = data.shape[1] if data.ndim == 2 else 1
        return data, channels, int(sr)
    except ImportError:
        pass
    except Exception as e:
        _log.debug("soundfile failed for %s: %s", path, e)

    # Try scipy
    try:
        from scipy.io import wavfile
        sr, data = wavfile.read(path)
        data = np.asarray(data, dtype=np.float32)
        if data.dtype != np.float32:
            # int16 → float32
            if data.max() > 1.0:
                data = data / 32768.0
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        channels = data.shape[1]
        return data, channels, int(sr)
    except ImportError:
        pass
    except Exception as e:
        _log.debug("scipy failed for %s: %s", path, e)

    _log.warning("Could not load audio: %s", path)
    return None


def _file_hash(path: str) -> str:
    """Quick hash for change detection: path + mtime + size."""
    try:
        stat = os.stat(path)
        raw = f"{path}:{stat.st_mtime_ns}:{stat.st_size}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Sample Syncer
# ---------------------------------------------------------------------------

class RustSampleSyncer:
    """Sends audio sample data to the Rust engine.

    Scans the project for audio clips, loads WAVs from disk, encodes
    as Base64 f32 LE, and sends LoadAudioClip commands.

    Also sends SetArrangement with all clip placements.
    """

    def __init__(self, bridge: Any, project_service: Any):
        self._bridge = bridge
        self._project_svc = project_service
        self._sent_hashes: Dict[str, str] = {}  # clip_id → file_hash

    @property
    def _project(self):
        try:
            ctx = getattr(self._project_svc, "ctx", None)
            if ctx:
                return getattr(ctx, "project", None)
        except Exception:
            pass
        return None

    def sync_all(self, force: bool = False) -> int:
        """Send all audio clip data + arrangement to Rust.

        Args:
            force: If True, re-send all clips even if unchanged.

        Returns:
            Number of clips sent.
        """
        project = self._project
        bridge = self._bridge
        if project is None or bridge is None:
            return 0
        if not getattr(bridge, "_connected", False):
            return 0

        # Build track_id → index map
        all_tracks = list(getattr(project, "tracks", []) or [])
        tid_to_idx: Dict[str, int] = {}
        for i, trk in enumerate(all_tracks):
            tid_to_idx[str(getattr(trk, "id", ""))] = i

        all_clips = list(getattr(project, "clips", []) or [])
        sent = 0
        arrangement: List[Dict[str, Any]] = []

        for clip in all_clips:
            if getattr(clip, "launcher_only", False):
                continue
            if getattr(clip, "muted", False):
                continue

            cid = str(getattr(clip, "id", "") or "")
            kind = str(getattr(clip, "kind", "audio") or "audio")
            tid = str(getattr(clip, "track_id", "") or "")
            track_idx = tid_to_idx.get(tid, 0)

            start = float(getattr(clip, "start_beats", 0.0) or 0.0)
            length = float(getattr(clip, "length_beats", 4.0) or 4.0)
            gain = float(getattr(clip, "gain", 1.0) or 1.0)
            offset = float(getattr(clip, "offset_beats", 0.0) or 0.0)

            # Add to arrangement regardless of kind
            arrangement.append({
                "clip_id": cid,
                "track_index": track_idx,
                "start_beat": start,
                "end_beat": start + length,
                "offset_samples": 0,  # TODO: beat-to-sample conversion
                "gain": gain,
            })

            # Only send audio data for audio clips
            if kind != "audio":
                continue

            path = self._resolve_clip_path(clip, project)
            if not path:
                continue

            # Change detection
            fhash = _file_hash(path)
            if not force and cid in self._sent_hashes:
                if self._sent_hashes[cid] == fhash:
                    continue  # unchanged

            # Load
            result = _load_audio_file(path)
            if result is None:
                _log.warning("Clip %s: could not load %s", cid, path)
                continue

            data, channels, sr = result

            # Convert to interleaved f32 bytes
            try:
                flat = data.astype(np.float32).tobytes()
            except Exception as e:
                _log.error("Clip %s: tobytes failed: %s", cid, e)
                continue

            # Send (with chunking for large files)
            if len(flat) <= MAX_CHUNK_BYTES:
                bridge.load_audio_clip(cid, flat, channels, sr)
            else:
                self._send_chunked(cid, flat, channels, sr)

            self._sent_hashes[cid] = fhash
            sent += 1

        # Send arrangement
        try:
            bridge.set_arrangement(arrangement)
            _log.info("SetArrangement sent: %d clips", len(arrangement))
        except Exception as e:
            _log.error("SetArrangement failed: %s", e)

        _log.info("SampleSync: %d audio clips sent, %d arrangement entries",
                   sent, len(arrangement))
        return sent

    def sync_clip(self, clip_id: str) -> bool:
        """Send a single audio clip to Rust.

        Returns True if sent successfully.
        """
        project = self._project
        bridge = self._bridge
        if project is None or bridge is None:
            return False

        clip = next(
            (c for c in (getattr(project, "clips", []) or [])
             if str(getattr(c, "id", "")) == clip_id),
            None)
        if clip is None:
            return False

        path = self._resolve_clip_path(clip, project)
        if not path:
            return False

        result = _load_audio_file(path)
        if result is None:
            return False

        data, channels, sr = result
        flat = data.astype(np.float32).tobytes()
        bridge.load_audio_clip(clip_id, flat, channels, sr)
        self._sent_hashes[clip_id] = _file_hash(path)
        return True

    def _resolve_clip_path(self, clip: Any, project: Any) -> str:
        """Resolve the audio file path for a clip."""
        # Direct source_path
        sp = str(getattr(clip, "source_path", "") or "")
        if sp and os.path.isfile(sp):
            return sp

        # Media reference
        mid = str(getattr(clip, "media_id", "") or "")
        if mid:
            for media in (getattr(project, "media", []) or []):
                if str(getattr(media, "id", "")) == mid:
                    mp = str(getattr(media, "path", "") or "")
                    if mp and os.path.isfile(mp):
                        return mp

        # Try project directory + source_path
        try:
            proj_dir = getattr(self._project_svc, "project_dir", "")
            if proj_dir and sp:
                full = os.path.join(proj_dir, sp)
                if os.path.isfile(full):
                    return full
                # Try media subdirectory
                media_path = os.path.join(proj_dir, "media", sp)
                if os.path.isfile(media_path):
                    return media_path
        except Exception:
            pass

        return ""

    def _send_chunked(self, clip_id: str, data: bytes,
                      channels: int, sr: int) -> None:
        """Send large audio data in chunks.

        Each chunk gets a sub-ID: clip_id__chunk_0, clip_id__chunk_1, etc.
        The Rust side reassembles if needed, or treats each chunk as
        a separate clip segment.
        """
        bridge = self._bridge
        offset = 0
        chunk_idx = 0
        while offset < len(data):
            end = min(offset + MAX_CHUNK_BYTES, len(data))
            chunk = data[offset:end]
            cid = f"{clip_id}__chunk_{chunk_idx}" if chunk_idx > 0 else clip_id
            bridge.load_audio_clip(cid, chunk, channels, sr)
            offset = end
            chunk_idx += 1
            _log.debug("Sent chunk %d for %s (%d bytes)",
                       chunk_idx, clip_id, len(chunk))

    def clear_cache(self) -> None:
        """Clear the sent-hashes cache (forces full re-sync)."""
        self._sent_hashes.clear()

    def get_stats(self) -> Dict[str, int]:
        """Return sync statistics."""
        return {
            "cached_clips": len(self._sent_hashes),
        }

    # ------------------------------------------------------------------
    # v0.0.20.711: RA2 Extended — DrumMachine, MultiSample, SF2, Wavetable
    # ------------------------------------------------------------------

    def sync_drum_pads(self, track_id: str, drum_state: dict) -> int:
        """Send DrumMachine pad samples to Rust.

        Args:
            track_id: Track ID owning the drum machine
            drum_state: DrumMachineEngine.get_state() dict with 'slots' list

        Returns:
            Number of pad samples sent.
        """
        bridge = self._bridge
        if bridge is None or not getattr(bridge, "_connected", False):
            return 0

        slots = drum_state.get("slots", []) or []
        sent = 0

        for slot in slots:
            if not isinstance(slot, dict):
                continue
            idx = int(slot.get("index", 0))
            sp = str(slot.get("sample_path", "") or "")
            if not sp or not os.path.isfile(sp):
                continue

            clip_id = f"drum:{track_id}:pad_{idx}"

            # Change detection
            fhash = _file_hash(sp)
            if clip_id in self._sent_hashes and self._sent_hashes[clip_id] == fhash:
                continue

            result = _load_audio_file(sp)
            if result is None:
                continue

            data, channels, sr = result
            try:
                flat = data.astype(np.float32).tobytes()
                bridge.load_audio_clip(clip_id, flat, channels, sr)
                self._sent_hashes[clip_id] = fhash
                sent += 1
            except Exception as e:
                _log.debug("DrumPad %s sync failed: %s", clip_id, e)

        if sent > 0:
            _log.info("DrumPad sync (%s): %d pads sent", track_id, sent)
        return sent

    def sync_multisample_zones(self, track_id: str, zones: list) -> int:
        """Send MultiSample zone samples to Rust.

        Args:
            track_id: Track ID owning the multi-sampler
            zones: List of SampleZone dicts (from MultiSampleMap.to_dict())

        Returns:
            Number of zone samples sent.
        """
        bridge = self._bridge
        if bridge is None or not getattr(bridge, "_connected", False):
            return 0

        sent = 0
        for i, zone in enumerate(zones):
            if not isinstance(zone, dict):
                continue
            sp = str(zone.get("sample_path", "") or "")
            if not sp or not os.path.isfile(sp):
                continue

            key_lo = int(zone.get("key_range_lo", 0))
            key_hi = int(zone.get("key_range_hi", 127))
            vel_lo = int(zone.get("vel_range_lo", 0))
            vel_hi = int(zone.get("vel_range_hi", 127))
            root = int(zone.get("root_key", 60))

            clip_id = f"zone:{track_id}:z{i}_k{key_lo}-{key_hi}_v{vel_lo}-{vel_hi}"

            fhash = _file_hash(sp)
            if clip_id in self._sent_hashes and self._sent_hashes[clip_id] == fhash:
                continue

            result = _load_audio_file(sp)
            if result is None:
                continue

            data, channels, sr = result
            try:
                flat = data.astype(np.float32).tobytes()
                bridge.load_audio_clip(clip_id, flat, channels, sr)
                # Also send zone mapping metadata
                bridge.send_command({
                    "cmd": "MapSampleZone",
                    "track_id": track_id,
                    "clip_id": clip_id,
                    "key_lo": key_lo,
                    "key_hi": key_hi,
                    "vel_lo": vel_lo,
                    "vel_hi": vel_hi,
                    "root_key": root,
                    "rr_group": int(zone.get("rr_group", 0)),
                })
                self._sent_hashes[clip_id] = fhash
                sent += 1
            except Exception as e:
                _log.debug("Zone %s sync failed: %s", clip_id, e)

        if sent > 0:
            _log.info("MultiSample sync (%s): %d zones sent", track_id, sent)
        return sent

    def sync_sf2(self, track_id: str, sf2_path: str,
                 bank: int = 0, preset: int = 0) -> bool:
        """Send SoundFont path to Rust (Rust loads directly from disk).

        Args:
            track_id: Track ID using the SF2
            sf2_path: Absolute path to the .sf2 file
            bank: MIDI bank number
            preset: MIDI program number

        Returns:
            True if command sent successfully.
        """
        bridge = self._bridge
        if bridge is None or not getattr(bridge, "_connected", False):
            return False

        if not sf2_path or not os.path.isfile(sf2_path):
            _log.warning("SF2 sync: file not found: %s", sf2_path)
            return False

        try:
            ok = bridge.send_command({
                "cmd": "LoadSF2",
                "track_id": track_id,
                "sf2_path": sf2_path,
                "bank": bank,
                "preset": preset,
            })
            if ok:
                _log.info("SF2 sync (%s): %s bank=%d preset=%d",
                          track_id, os.path.basename(sf2_path), bank, preset)
            return ok
        except Exception as e:
            _log.error("SF2 sync failed: %s", e)
            return False

    def sync_wavetable(self, track_id: str, wt_bank: Any) -> bool:
        """Send wavetable frame data to Rust.

        Args:
            track_id: Track ID of the AETERNA synth
            wt_bank: WavetableBank instance (from aeterna)

        Returns:
            True if sent successfully.
        """
        bridge = self._bridge
        if bridge is None or not getattr(bridge, "_connected", False):
            return False
        if not _NP:
            return False

        try:
            frames = getattr(wt_bank, "_frames", []) or []
            frame_size = int(getattr(wt_bank, "_frame_size", 2048) or 2048)
            num_frames = len(frames)
            table_name = str(getattr(wt_bank, "_table_name", "") or "")

            if num_frames == 0:
                return False

            # Concatenate all frames into a single f32 array
            concat = np.zeros(num_frames * frame_size, dtype=np.float32)
            for i, frame in enumerate(frames):
                arr = np.asarray(frame, dtype=np.float32)
                n = min(len(arr), frame_size)
                concat[i * frame_size : i * frame_size + n] = arr[:n]

            raw_b64 = base64.b64encode(concat.tobytes()).decode("ascii")

            ok = bridge.send_command({
                "cmd": "LoadWavetable",
                "track_id": track_id,
                "table_name": table_name,
                "frame_size": frame_size,
                "num_frames": num_frames,
                "data_b64": raw_b64,
            })
            if ok:
                _log.info("Wavetable sync (%s): '%s' %d frames × %d",
                          track_id, table_name, num_frames, frame_size)
            return ok
        except Exception as e:
            _log.error("Wavetable sync failed: %s", e)
            return False

    def sync_all_instruments(self) -> Dict[str, int]:
        """Scan all tracks and sync instrument samples to Rust.

        Handles DrumMachine pads, MultiSample zones, SF2, and Wavetable.

        Returns:
            Dict with counts: {"drums": N, "zones": N, "sf2": N, "wavetables": N}
        """
        project = self._project
        if project is None:
            return {"drums": 0, "zones": 0, "sf2": 0, "wavetables": 0}

        counts = {"drums": 0, "zones": 0, "sf2": 0, "wavetables": 0}
        all_tracks = list(getattr(project, "tracks", []) or [])

        for trk in all_tracks:
            tid = str(getattr(trk, "id", "") or "")
            ptype = str(getattr(trk, "plugin_type", "") or "")

            # DrumMachine
            if "drum" in ptype.lower():
                try:
                    engine = getattr(trk, "_instrument_engine", None)
                    if engine and hasattr(engine, "get_state"):
                        state = engine.get_state()
                        counts["drums"] += self.sync_drum_pads(tid, state)
                except Exception:
                    pass

            # MultiSample / ProSampler with zones
            elif "sampler" in ptype.lower() or "multisample" in ptype.lower():
                try:
                    engine = getattr(trk, "_instrument_engine", None)
                    if engine and hasattr(engine, "get_zone_dicts"):
                        zones = engine.get_zone_dicts()
                        counts["zones"] += self.sync_multisample_zones(tid, zones)
                    elif engine and hasattr(engine, "get_state"):
                        state = engine.get_state()
                        zones = state.get("zones", []) or []
                        counts["zones"] += self.sync_multisample_zones(tid, zones)
                except Exception:
                    pass

            # SF2
            elif ptype == "sf2":
                try:
                    sp = str(getattr(trk, "sf2_path", "") or "")
                    bank = int(getattr(trk, "sf2_bank", 0) or 0)
                    preset = int(getattr(trk, "sf2_preset", 0) or 0)
                    if sp:
                        if self.sync_sf2(tid, sp, bank, preset):
                            counts["sf2"] += 1
                except Exception:
                    pass

            # AETERNA with wavetable
            elif "aeterna" in ptype.lower():
                try:
                    engine = getattr(trk, "_instrument_engine", None)
                    if engine:
                        for osc_attr in ("_wt_bank", "wt_bank", "_wavetable_bank"):
                            wt = getattr(engine, osc_attr, None)
                            if wt and hasattr(wt, "_frames"):
                                if self.sync_wavetable(tid, wt):
                                    counts["wavetables"] += 1
                                break
                except Exception:
                    pass

        _log.info("Instrument sync: drums=%d, zones=%d, sf2=%d, wavetables=%d",
                  counts["drums"], counts["zones"], counts["sf2"], counts["wavetables"])
        return counts
