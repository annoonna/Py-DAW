"""DAWproject Exporter — safe, snapshot-based .dawproject export scaffold.

This module intentionally stays **outside** the running audio / transport core.
It builds a read-only snapshot of the current Project model, maps it to a
DAWproject-like XML/ZIP container, and writes the result via a
"temp-file-first" pipeline.

Goals of this safe scaffold:
- no mutation of the live session while exporting
- no direct dependency on playback state or DSP objects
- non-blocking UI integration via QRunnable (optional, PyQt6-aware)
- conservative XML generation using stdlib ``xml.etree.ElementTree``
- archive validation before atomically moving the finished file into place

Notes:
- This is a **high-level exporter foundation**. It writes transport, tracks,
  clips, notes, automation lanes, audio references and generic embedded plugin
  state blobs.
- It does **not** try to perfectly roundtrip every foreign DAW feature yet.
- Plugin state export is implemented as Base64-encoded payloads in XML so the
  data flow is present without touching the engine.

v0.0.20.358 — Initial safe export architecture scaffold (GPT-5, 2026-03-08)
"""

from __future__ import annotations

import base64
import copy
import json
import logging
import os
import shutil
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from pydaw.model.midi import MidiNote
from pydaw.model.project import Clip, MediaItem, Project, Track
from pydaw.version import __version__

log = logging.getLogger(__name__)

try:  # optional UI integration
    from PyQt6.QtCore import QObject, QRunnable, pyqtSignal
    PYQT_AVAILABLE = True
except Exception:  # pragma: no cover
    QObject = object  # type: ignore[assignment]
    QRunnable = object  # type: ignore[assignment]
    pyqtSignal = None  # type: ignore[assignment]
    PYQT_AVAILABLE = False

ProgressCallback = Callable[[int, str], None]


@dataclass(frozen=True)
class ExportAudioRef:
    """Resolved audio file to be copied into the .dawproject archive."""

    source_path: Path
    archive_path: str
    media_id: str = ""


@dataclass
class DawProjectExportRequest:
    """Immutable-ish request object for one export job."""

    snapshot: Project
    target_path: Path
    project_root: Optional[Path] = None
    include_media: bool = True
    validate_archive: bool = True
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class DawProjectExportResult:
    """Summary of one export run."""

    output_path: Path
    tracks_exported: int = 0
    clips_exported: int = 0
    notes_exported: int = 0
    automation_lanes_exported: int = 0
    audio_files_copied: int = 0
    plugin_states_embedded: int = 0
    warnings: List[str] = field(default_factory=list)


class DawProjectSnapshotFactory:
    """Creates a detached snapshot copy from the live Project model.

    The snapshot is built from a deep-copied JSON-safe dict representation so
    all nested dataclasses/lists/dicts are detached from the live session.
    """

    @staticmethod
    def from_live_project(project: Project) -> Project:
        raw = copy.deepcopy(project.to_dict())
        return Project.from_dict(raw)


class DawProjectExporter:
    """Pure data-mapper that writes a Project snapshot as .dawproject."""

    def __init__(
        self,
        snapshot: Project,
        project_root: Optional[Path] = None,
        progress_cb: Optional[ProgressCallback] = None,
    ):
        self.project = DawProjectSnapshotFactory.from_live_project(snapshot)
        self.project_root = Path(project_root) if project_root else None
        self.progress_cb: ProgressCallback = progress_cb or (lambda pct, msg: None)
        self._media_by_id = {
            str(getattr(m, "id", "")): m
            for m in (getattr(self.project, "media", []) or [])
            if str(getattr(m, "id", ""))
        }
        self._track_order = [t for t in (getattr(self.project, "tracks", []) or [])]
        self._clips_by_track: Dict[str, List[Clip]] = {}
        for clip in (getattr(self.project, "clips", []) or []):
            tid = str(getattr(clip, "track_id", "") or "")
            self._clips_by_track.setdefault(tid, []).append(clip)
        for clips in self._clips_by_track.values():
            clips.sort(key=lambda c: (float(getattr(c, "start_beats", 0.0) or 0.0), str(getattr(c, "id", ""))))

    def run(
        self,
        target_path: Path,
        *,
        include_media: bool = True,
        validate_archive: bool = True,
        metadata: Optional[Dict[str, str]] = None,
    ) -> DawProjectExportResult:
        """Export the snapshot to ``target_path``.

        The archive is first assembled in a temporary staging directory. The
        final ZIP is then written to a temporary sibling file inside the target
        directory, validated, and finally moved into place with ``os.replace``.
        This avoids cross-device rename failures between ``/tmp`` and user
        folders on other filesystems.
        """
        out_path = Path(target_path)
        if out_path.suffix.lower() != ".dawproject":
            out_path = out_path.with_suffix(".dawproject")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        result = DawProjectExportResult(output_path=out_path)

        self.progress_cb(2, "Snapshot export vorbereiten …")
        audio_refs: Dict[str, ExportAudioRef] = self._collect_audio_references(include_media, result)

        sibling_tmp_output: Optional[Path] = None
        try:
            with tempfile.TemporaryDirectory(prefix="pydaw_dawproject_export_") as tmp_dir_str:
                tmp_dir = Path(tmp_dir_str)
                staging = tmp_dir / "stage"
                staging.mkdir(parents=True, exist_ok=True)
                (staging / "audio").mkdir(exist_ok=True)
                (staging / "plugins").mkdir(exist_ok=True)

                self.progress_cb(15, "XML-Struktur erstellen …")
                metadata_tree = self._build_metadata_tree(metadata or {})
                project_tree = self._build_project_tree(audio_refs, result)
                self._write_xml(staging / "metadata.xml", metadata_tree)
                self._write_xml(staging / "project.xml", project_tree)

                if include_media:
                    self.progress_cb(45, "Audio-Dateien in Staging kopieren …")
                    self._stage_audio_files(staging, audio_refs, result)

                with tempfile.NamedTemporaryFile(
                    prefix=f".{out_path.stem}_",
                    suffix=".dawproject.tmp",
                    dir=str(out_path.parent),
                    delete=False,
                ) as tmp_file:
                    sibling_tmp_output = Path(tmp_file.name)

                self.progress_cb(72, "ZIP-Container schreiben …")
                self._build_zip_archive(staging, sibling_tmp_output)

                if validate_archive:
                    self.progress_cb(88, "Archiv validieren …")
                    self._validate_archive(sibling_tmp_output)

                self.progress_cb(96, "Archiv atomar übernehmen …")
                os.replace(sibling_tmp_output, out_path)
                sibling_tmp_output = None
        finally:
            if sibling_tmp_output is not None:
                try:
                    sibling_tmp_output.unlink(missing_ok=True)
                except Exception:
                    pass

        self.progress_cb(100, "DAWproject Export abgeschlossen")
        return result

    # ------------------------------------------------------------------
    # Snapshot/resolve helpers
    # ------------------------------------------------------------------

    def _resolve_fs_path(self, raw_path: str) -> Optional[Path]:
        if not raw_path:
            return None
        p = Path(raw_path)
        if p.is_absolute():
            return p if p.exists() else None
        if self.project_root is not None:
            candidate = self.project_root / p
            if candidate.exists():
                return candidate
        cwd_candidate = Path.cwd() / p
        if cwd_candidate.exists():
            return cwd_candidate
        return None

    def _collect_audio_references(
        self,
        include_media: bool,
        result: DawProjectExportResult,
    ) -> Dict[str, ExportAudioRef]:
        refs: Dict[str, ExportAudioRef] = {}
        used_names: set[str] = set()

        if not include_media:
            return refs

        def unique_arc_name(name: str) -> str:
            clean = Path(name).name or "audio.wav"
            stem = Path(clean).stem or "audio"
            suffix = Path(clean).suffix or ".wav"
            candidate = f"audio/{clean}"
            counter = 1
            while candidate.lower() in used_names:
                candidate = f"audio/{stem}_{counter}{suffix}"
                counter += 1
            used_names.add(candidate.lower())
            return candidate

        # 1) explicit project media items
        for media in (getattr(self.project, "media", []) or []):
            if str(getattr(media, "kind", "")) != "audio":
                continue
            raw_path = str(getattr(media, "path", "") or "")
            src = self._resolve_fs_path(raw_path)
            if not src:
                result.warnings.append(f"Audio-Media fehlt und wird übersprungen: {raw_path}")
                continue
            refs[str(getattr(media, "id", "") or raw_path)] = ExportAudioRef(
                source_path=src,
                archive_path=unique_arc_name(src.name),
                media_id=str(getattr(media, "id", "") or ""),
            )

        # 2) audio clips that only carry source_path
        for clip in (getattr(self.project, "clips", []) or []):
            if str(getattr(clip, "kind", "")) != "audio":
                continue
            media_id = str(getattr(clip, "media_id", "") or "")
            if media_id and media_id in refs:
                continue
            raw_path = str(getattr(clip, "source_path", "") or "")
            if not raw_path:
                continue
            src = self._resolve_fs_path(raw_path)
            if not src:
                result.warnings.append(f"Audio-Clip Quelle fehlt und wird übersprungen: {raw_path}")
                continue
            key = f"clip:{getattr(clip, 'id', '')}"
            refs[key] = ExportAudioRef(source_path=src, archive_path=unique_arc_name(src.name))

        return refs

    # ------------------------------------------------------------------
    # XML generation
    # ------------------------------------------------------------------

    def _build_metadata_tree(self, metadata: Dict[str, str]) -> ET.ElementTree:
        root = ET.Element("MetaData")
        ET.SubElement(root, "Title").text = str(metadata.get("title") or getattr(self.project, "name", "PyDAW Export") or "PyDAW Export")
        ET.SubElement(root, "Artist").text = str(metadata.get("artist") or "")
        ET.SubElement(root, "Comment").text = str(metadata.get("comment") or "")
        ET.SubElement(root, "Application").text = "ChronoScaleStudio"
        ET.SubElement(root, "ApplicationVersion").text = str(__version__)
        return ET.ElementTree(root)

    def _build_project_tree(
        self,
        audio_refs: Dict[str, ExportAudioRef],
        result: DawProjectExportResult,
    ) -> ET.ElementTree:
        root = ET.Element("Project")
        root.set("version", "1.0")

        ET.SubElement(root, "Application", name="ChronoScaleStudio", version=str(__version__))
        self._append_transport(root)
        self._append_structure(root, result)
        self._append_arrangement(root, audio_refs, result)
        self._append_global_notes(root)
        return ET.ElementTree(root)

    def _append_transport(self, root: ET.Element) -> None:
        transport = ET.SubElement(root, "Transport")
        ET.SubElement(transport, "Tempo", value=f"{float(getattr(self.project, 'bpm', 120.0) or 120.0):.6f}")
        num, den = self._parse_time_signature(str(getattr(self.project, "time_signature", "4/4") or "4/4"))
        ET.SubElement(transport, "TimeSignature", numerator=str(num), denominator=str(den))

    def _append_structure(self, root: ET.Element, result: DawProjectExportResult) -> None:
        structure = ET.SubElement(root, "Structure")
        for track in self._track_order:
            if str(getattr(track, "kind", "")) == "master":
                self._append_track_element(structure, track, role="master", result=result)
                continue
            self._append_track_element(structure, track, role="track", result=result)

    def _append_track_element(self, parent: ET.Element, track: Track, *, role: str, result: DawProjectExportResult) -> None:
        trk_elem = ET.SubElement(
            parent,
            "Track",
            id=str(getattr(track, "id", "") or ""),
            name=str(getattr(track, "name", "Track") or "Track"),
            contentType=self._track_content_type(track),
            role=role,
        )
        kind = str(getattr(track, "kind", "") or "")
        if kind:
            trk_elem.set("pydawKind", kind)
        group_id = str(getattr(track, "track_group_id", "") or "")
        if group_id:
            trk_elem.set("groupId", group_id)
        group_name = str(getattr(track, "track_group_name", "") or "")
        if group_name:
            trk_elem.set("groupName", group_name)

        channel = ET.SubElement(trk_elem, "Channel")
        ET.SubElement(channel, "Volume", value=f"{self._to_dawproject_volume(float(getattr(track, 'volume', 0.8) or 0.8)):.6f}")
        ET.SubElement(channel, "Pan", value=f"{self._to_dawproject_pan(float(getattr(track, 'pan', 0.0) or 0.0)):.6f}")
        ET.SubElement(channel, "Mute", value=str(bool(getattr(track, "muted", False))).lower())
        ET.SubElement(channel, "Solo", value=str(bool(getattr(track, "solo", False))).lower())

        devices = ET.SubElement(channel, "Devices")
        self._append_track_devices(devices, track, result)

        # v0.0.20.658: Export sends
        sends = getattr(track, "sends", []) or []
        if sends:
            sends_elem = ET.SubElement(channel, "Sends")
            for send in sends:
                if not isinstance(send, dict):
                    continue
                send_elem = ET.SubElement(
                    sends_elem,
                    "Send",
                    destination=str(send.get("target_track_id", "") or ""),
                    volume=f"{float(send.get('amount', 0.5) or 0.5):.6f}",
                )
                if send.get("pre_fader"):
                    send_elem.set("preFader", "true")

        result.tracks_exported += 1

    def _append_track_devices(self, devices_elem: ET.Element, track: Track, result: DawProjectExportResult) -> None:
        plugin_type = str(getattr(track, "plugin_type", "") or "")
        if plugin_type:
            # v0.0.20.658: Use plugin mapping for spec-compliant deviceIDs
            mapped_device_id = self._map_plugin_id(plugin_type)
            inst_elem = ET.SubElement(
                devices_elem,
                "Plugin",
                role="instrument",
                name=plugin_type,
                deviceID=mapped_device_id,
                enabled=str(bool(getattr(track, "instrument_enabled", True))).lower(),
                format=self._plugin_format_from_id(plugin_type),
            )
            state_payload = getattr(track, "instrument_state", {}) or {}
            self._append_state_blob(inst_elem, state_payload, result)

        self._append_chain_devices(devices_elem, track, "note_fx_chain", "note-fx", result)
        self._append_chain_devices(devices_elem, track, "audio_fx_chain", "audio-fx", result)

    def _append_chain_devices(
        self,
        devices_elem: ET.Element,
        track: Track,
        chain_attr: str,
        role: str,
        result: DawProjectExportResult,
    ) -> None:
        chain = getattr(track, chain_attr, None)
        if not isinstance(chain, dict):
            return
        chain_elem = ET.SubElement(
            devices_elem,
            "DeviceChain",
            role=role,
            enabled=str(bool(chain.get("enabled", True))).lower(),
            mix=f"{float(chain.get('mix', 1.0) or 1.0):.6f}",
            wetGain=f"{float(chain.get('wet_gain', 1.0) or 1.0):.6f}",
        )
        for dev in (chain.get("devices", []) or []):
            if not isinstance(dev, dict):
                continue
            pid = str(dev.get("plugin_id") or dev.get("type") or dev.get("name") or "device")
            mapped_id = self._map_plugin_id(pid)
            dev_elem = ET.SubElement(
                chain_elem,
                "Plugin",
                role=role,
                name=str(dev.get("name") or pid),
                deviceID=mapped_id,
                enabled=str(bool(dev.get("enabled", True))).lower(),
                format=self._plugin_format_from_id(pid),
            )
            if dev.get("id"):
                dev_elem.set("id", str(dev.get("id")))
            params = dev.get("params") if isinstance(dev.get("params"), dict) else {}
            if params:
                params_elem = ET.SubElement(dev_elem, "Parameters")
                for key, value in sorted(params.items(), key=lambda kv: str(kv[0])):
                    ET.SubElement(params_elem, "Parameter", id=str(key), value=self._scalar_to_text(value))
            state_payload = self._extract_plugin_state_payload(dev)
            self._append_state_blob(dev_elem, state_payload, result)

    def _append_arrangement(
        self,
        root: ET.Element,
        audio_refs: Dict[str, ExportAudioRef],
        result: DawProjectExportResult,
    ) -> None:
        arrangement = ET.SubElement(root, "Arrangement")
        lanes_root = ET.SubElement(arrangement, "Lanes")
        for track in self._track_order:
            if str(getattr(track, "kind", "")) == "master":
                continue
            track_lanes = ET.SubElement(lanes_root, "Lanes", track=str(getattr(track, "id", "") or ""))
            clips = self._clips_by_track.get(str(getattr(track, "id", "") or ""), [])
            if clips:
                clips_elem = ET.SubElement(track_lanes, "Clips")
                for clip in clips:
                    self._append_clip(clips_elem, clip, audio_refs, result)
            lane_count = self._append_track_automation_lanes(track_lanes, track)
            result.automation_lanes_exported += lane_count

    def _append_clip(
        self,
        clips_elem: ET.Element,
        clip: Clip,
        audio_refs: Dict[str, ExportAudioRef],
        result: DawProjectExportResult,
    ) -> None:
        clip_elem = ET.SubElement(
            clips_elem,
            "Clip",
            id=str(getattr(clip, "id", "") or ""),
            time=f"{float(getattr(clip, 'start_beats', 0.0) or 0.0):.6f}",
            duration=f"{max(0.0, float(getattr(clip, 'length_beats', 0.0) or 0.0)):.6f}",
            contentTimeOffset=f"{float(getattr(clip, 'offset_beats', 0.0) or 0.0):.6f}",
            name=str(getattr(clip, "label", "Clip") or "Clip"),
        )
        if bool(getattr(clip, "muted", False)):
            clip_elem.set("muted", "true")
        if bool(getattr(clip, "reversed", False)):
            clip_elem.set("reversed", "true")
        if getattr(clip, "group_id", ""):
            clip_elem.set("groupId", str(getattr(clip, "group_id", "")))

        if str(getattr(clip, "kind", "")) == "midi":
            notes_elem = ET.SubElement(clip_elem, "Notes")
            notes = list((getattr(self.project, "midi_notes", {}) or {}).get(str(getattr(clip, "id", "") or ""), []) or [])
            notes.sort(key=lambda n: (float(getattr(n, "start_beats", 0.0) or 0.0), int(getattr(n, "pitch", 0) or 0)))
            for note in notes:
                self._append_note(notes_elem, note)
                result.notes_exported += 1
        elif str(getattr(clip, "kind", "")) == "audio":
            audio_elem = ET.SubElement(clip_elem, "Audio")
            ref = self._lookup_audio_ref(clip, audio_refs)
            if ref is not None:
                ET.SubElement(audio_elem, "File", path=ref.archive_path)
            else:
                raw_path = str(getattr(clip, "source_path", "") or "")
                if raw_path:
                    ET.SubElement(audio_elem, "File", path=raw_path)

        self._append_clip_extensions(clip_elem, clip)
        result.clips_exported += 1

    def _append_note(self, notes_elem: ET.Element, note: MidiNote) -> None:
        note_elem = ET.SubElement(
            notes_elem,
            "Note",
            time=f"{float(getattr(note, 'start_beats', 0.0) or 0.0):.6f}",
            duration=f"{float(getattr(note, 'length_beats', 0.0) or 0.0):.6f}",
            key=str(int(getattr(note, "pitch", 60) or 60)),
            vel=f"{max(0.0, min(1.0, float(int(getattr(note, 'velocity', 100) or 100) / 127.0))):.6f}",
            channel="0",
        )
        expressions = getattr(note, "expressions", {}) or {}
        if isinstance(expressions, dict) and expressions:
            exprs = ET.SubElement(note_elem, "NoteExpressions")
            for name, points in sorted(expressions.items(), key=lambda kv: str(kv[0])):
                lane = ET.SubElement(exprs, "Expression", id=str(name))
                for point in (points or []):
                    if not isinstance(point, dict):
                        continue
                    ET.SubElement(
                        lane,
                        "Point",
                        t=f"{float(point.get('t', 0.0) or 0.0):.6f}",
                        v=self._scalar_to_text(point.get("v", 0.0)),
                    )

    def _append_clip_extensions(self, clip_elem: ET.Element, clip: Clip) -> None:
        ext = ET.SubElement(clip_elem, "Extensions", source="ChronoScaleStudio")
        ET.SubElement(ext, "Gain", value=self._scalar_to_text(getattr(clip, "gain", 1.0)))
        ET.SubElement(ext, "Pan", value=self._scalar_to_text(getattr(clip, "pan", 0.0)))
        ET.SubElement(ext, "Pitch", value=self._scalar_to_text(getattr(clip, "pitch", 0.0)))
        ET.SubElement(ext, "Stretch", value=self._scalar_to_text(getattr(clip, "stretch", 1.0)))
        clip_auto = getattr(clip, "clip_automation", {}) or {}
        if isinstance(clip_auto, dict) and clip_auto:
            clip_auto_elem = ET.SubElement(ext, "ClipAutomation")
            for name, points in sorted(clip_auto.items(), key=lambda kv: str(kv[0])):
                lane_elem = ET.SubElement(clip_auto_elem, "Lane", id=str(name))
                for point in (points or []):
                    if not isinstance(point, dict):
                        continue
                    ET.SubElement(
                        lane_elem,
                        "Point",
                        beat=self._scalar_to_text(point.get("beat", 0.0)),
                        value=self._scalar_to_text(point.get("value", 0.0)),
                    )

    def _append_track_automation_lanes(self, track_lanes: ET.Element, track: Track) -> int:
        raw_lanes = getattr(self.project, "automation_manager_lanes", {}) or {}
        if not isinstance(raw_lanes, dict):
            return 0
        lanes_for_track: List[Tuple[str, dict]] = []
        track_id = str(getattr(track, "id", "") or "")
        for pid, lane in raw_lanes.items():
            if not isinstance(lane, dict):
                continue
            if str(lane.get("track_id", "") or "") != track_id:
                continue
            lanes_for_track.append((str(pid), lane))
        if not lanes_for_track:
            return 0

        auto_elem = ET.SubElement(track_lanes, "AutomationLanes")
        count = 0
        for pid, lane in sorted(lanes_for_track, key=lambda item: item[0]):
            lane_elem = ET.SubElement(
                auto_elem,
                "AutomationLane",
                parameterID=pid,
                name=str(lane.get("param_name", "") or pid),
                enabled=str(bool(lane.get("enabled", True))).lower(),
                color=str(lane.get("color", "#00BFFF") or "#00BFFF"),
            )
            points_elem = ET.SubElement(lane_elem, "Points")
            for point in (lane.get("points", []) or []):
                if not isinstance(point, dict):
                    continue
                attrs = {
                    "time": self._scalar_to_text(point.get("beat", 0.0)),
                    "value": self._scalar_to_text(point.get("value", 0.0)),
                    "interpolation": str(point.get("curve_type", "linear") or "linear"),
                }
                if "bezier_cx" in point:
                    attrs["bezierCx"] = self._scalar_to_text(point.get("bezier_cx", 0.5))
                if "bezier_cy" in point:
                    attrs["bezierCy"] = self._scalar_to_text(point.get("bezier_cy", 0.5))
                ET.SubElement(points_elem, "Point", **attrs)
            count += 1
        return count

    def _append_global_notes(self, root: ET.Element) -> None:
        notes = ET.SubElement(root, "Notes")
        notes.text = "Exported by ChronoScaleStudio snapshot-based DAWproject exporter scaffold"

    # ------------------------------------------------------------------
    # Plugin state handling
    # ------------------------------------------------------------------

    def _extract_plugin_state_payload(self, device: Dict[str, Any]) -> Any:
        for key in (
            "plugin_state",
            "state",
            "state_blob",
            "preset_blob",
            "chunk",
            "raw_state",
        ):
            if key in device:
                return device.get(key)
        # Fallback: serialise the whole device spec so the export keeps enough
        # structural information for later refinement.
        return device

    def _append_state_blob(self, parent: ET.Element, payload: Any, result: DawProjectExportResult) -> None:
        if payload is None:
            return
        try:
            blob = self._encode_payload(payload)
        except Exception as exc:
            result.warnings.append(f"Plugin-State konnte nicht serialisiert werden: {exc}")
            return
        if not blob:
            return
        state_elem = ET.SubElement(parent, "State", encoding="base64", contentType="application/json")
        state_elem.text = blob
        result.plugin_states_embedded += 1

    @staticmethod
    def _encode_payload(payload: Any) -> str:
        if payload is None:
            return ""
        if isinstance(payload, bytes):
            raw = payload
        elif isinstance(payload, str):
            raw = payload.encode("utf-8")
        else:
            raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    # ------------------------------------------------------------------
    # ZIP / file writing
    # ------------------------------------------------------------------

    def _stage_audio_files(
        self,
        staging_root: Path,
        audio_refs: Dict[str, ExportAudioRef],
        result: DawProjectExportResult,
    ) -> None:
        total = max(1, len(audio_refs))
        for idx, ref in enumerate(audio_refs.values(), start=1):
            rel = Path(ref.archive_path)
            dest = staging_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ref.source_path, dest)
            result.audio_files_copied += 1
            pct = 45 + int(20 * (idx / total))
            self.progress_cb(pct, f"Audio: {ref.source_path.name}")

    def _build_zip_archive(self, staging_root: Path, output_zip: Path) -> None:
        with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for file_path in sorted(staging_root.rglob("*")):
                if not file_path.is_file():
                    continue
                arcname = file_path.relative_to(staging_root).as_posix()
                zf.write(file_path, arcname)

    def _validate_archive(self, archive_path: Path) -> None:
        if not zipfile.is_zipfile(archive_path):
            raise ValueError(f"Keine gültige .dawproject ZIP-Datei erzeugt: {archive_path}")
        with zipfile.ZipFile(archive_path, "r") as zf:
            names = set(zf.namelist())
            required = {"project.xml", "metadata.xml"}
            missing = sorted(required.difference(names))
            if missing:
                raise ValueError(f"Pflichtdateien im Export fehlen: {', '.join(missing)}")
            with zf.open("project.xml") as f:
                ET.parse(f)
            with zf.open("metadata.xml") as f:
                ET.parse(f)

    @staticmethod
    def _write_xml(path: Path, tree: ET.ElementTree) -> None:
        if hasattr(ET, "indent"):
            try:
                ET.indent(tree, space="  ")
            except Exception:
                pass
        tree.write(path, encoding="utf-8", xml_declaration=True)

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _track_content_type(track: Track) -> str:
        kind = str(getattr(track, "kind", "") or "")
        plugin_type = str(getattr(track, "plugin_type", "") or "")
        if kind in ("instrument", "group") or plugin_type:
            return "notes"
        return "audio"

    @staticmethod
    def _plugin_format_from_id(plugin_id: str) -> str:
        pid = str(plugin_id or "").lower()
        if pid.startswith("clap"):
            return "CLAP"
        if pid.startswith("vst3"):
            return "VST3"
        if pid.startswith("ext.lv2") or pid.startswith("lv2"):
            return "LV2"
        if pid.startswith("ladspa"):
            return "LADSPA"
        if pid.startswith("chrono") or pid.startswith("internal"):
            return "INTERNAL"
        return "GENERIC"

    @staticmethod
    def _to_dawproject_volume(pydaw_volume: float) -> float:
        return max(0.0, min(2.0, float(pydaw_volume) / 0.8 if pydaw_volume is not None else 1.0))

    @staticmethod
    def _to_dawproject_pan(pydaw_pan: float) -> float:
        return max(0.0, min(1.0, (float(pydaw_pan) + 1.0) / 2.0))

    @staticmethod
    def _map_plugin_id(pydaw_plugin_id: str) -> str:
        """Map a Py_DAW plugin ID to a DAWproject-compliant deviceID."""
        try:
            from pydaw.fileio.dawproject_plugin_map import pydaw_id_to_dawproject_device_id
            result = pydaw_id_to_dawproject_device_id(pydaw_plugin_id)
            if result:
                return result
        except ImportError:
            pass
        return pydaw_plugin_id

    @staticmethod
    def _parse_time_signature(sig: str) -> Tuple[int, int]:
        try:
            num_s, den_s = str(sig or "4/4").split("/", 1)
            num = max(1, int(num_s))
            den = max(1, int(den_s))
            return num, den
        except Exception:
            return 4, 4

    @staticmethod
    def _scalar_to_text(value: Any) -> str:
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, int):
            return str(value)
        try:
            return f"{float(value):.6f}"
        except Exception:
            return str(value)

    def _lookup_audio_ref(self, clip: Clip, audio_refs: Dict[str, ExportAudioRef]) -> Optional[ExportAudioRef]:
        media_id = str(getattr(clip, "media_id", "") or "")
        if media_id and media_id in audio_refs:
            return audio_refs.get(media_id)
        clip_key = f"clip:{getattr(clip, 'id', '')}"
        if clip_key in audio_refs:
            return audio_refs.get(clip_key)
        raw_path = str(getattr(clip, "source_path", "") or "")
        if raw_path:
            for ref in audio_refs.values():
                if ref.source_path.name == Path(raw_path).name:
                    return ref
        return None


# ---------------------------------------------------------------------------
# Convenience helpers for service/UI integration
# ---------------------------------------------------------------------------


def build_dawproject_export_request(
    live_project: Project,
    target_path: Path,
    project_root: Optional[Path] = None,
    *,
    include_media: bool = True,
    validate_archive: bool = True,
    metadata: Optional[Dict[str, str]] = None,
) -> DawProjectExportRequest:
    """Create a detached export request from a live project."""
    snapshot = DawProjectSnapshotFactory.from_live_project(live_project)
    return DawProjectExportRequest(
        snapshot=snapshot,
        target_path=Path(target_path),
        project_root=Path(project_root) if project_root else None,
        include_media=include_media,
        validate_archive=validate_archive,
        metadata=dict(metadata or {}),
    )


def export_dawproject(
    request: DawProjectExportRequest,
    progress_cb: Optional[ProgressCallback] = None,
) -> DawProjectExportResult:
    """High-level synchronous entry point.

    Safe for background-thread use because it only consumes ``request.snapshot``.
    """
    exporter = DawProjectExporter(
        snapshot=request.snapshot,
        project_root=request.project_root,
        progress_cb=progress_cb,
    )
    return exporter.run(
        request.target_path,
        include_media=request.include_media,
        validate_archive=request.validate_archive,
        metadata=request.metadata,
    )


if PYQT_AVAILABLE:
    class DawProjectExportSignals(QObject):
        """Signals for a non-blocking export QRunnable."""

        progress = pyqtSignal(int, str)
        finished = pyqtSignal(object)
        error = pyqtSignal(str)


    class DawProjectExportRunnable(QRunnable):
        """QRunnable wrapper for snapshot-based export."""

        def __init__(self, request: DawProjectExportRequest):
            super().__init__()
            self.request = request
            self.signals = DawProjectExportSignals()

        def run(self) -> None:  # pragma: no cover - Qt thread wrapper
            try:
                result = export_dawproject(self.request, progress_cb=self.signals.progress.emit)
                self.signals.finished.emit(result)
            except Exception as exc:
                self.signals.error.emit(str(exc))

else:
    class DawProjectExportRunnable:  # pragma: no cover - fallback for headless importers
        def __init__(self, request: DawProjectExportRequest):
            self.request = request
            self.signals = None

        def run(self) -> DawProjectExportResult:
            return export_dawproject(self.request)
