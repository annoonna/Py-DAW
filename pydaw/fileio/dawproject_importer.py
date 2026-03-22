"""DAWproject Importer — Import .dawproject files (Bitwig/Studio One/Cubase).

DAWproject is an open exchange format for DAWs (https://github.com/bitwig/dawproject).
A .dawproject file is a ZIP archive containing:
  - project.xml  (track structure, clips, notes, automation, transport)
  - metadata.xml (title, artist, comments)
  - audio/       (referenced WAV/FLAC files)
  - plugins/     (plugin state files — CLAP/VST presets)

This importer maps DAWproject structures into PyDAW's internal model:
  - DAWproject Track → PyDAW Track (audio / instrument / group / fx)
  - DAWproject Clip + Notes → PyDAW Clip + MidiNotes
  - DAWproject Audio references → imported into project media/
  - DAWproject Transport (BPM, time signature) → project settings
  - DAWproject AutomationLanes → automation_manager_lanes
  - DAWproject Plugin States → instrument_state / audio_fx_chain blobs
  - DAWproject Sends → Track.sends
  - DAWproject Group/Folder hierarchy → track_group_id
  - DAWproject Clip Extensions → gain, pan, pitch, stretch, muted, reversed

v0.0.20.88  — Initial implementation (Claude Opus 4.6, 2026-02-16)
v0.0.20.658 — Full roundtrip: automation, plugins, sends, groups (Claude Opus 4.6, 2026-03-20)
"""

from __future__ import annotations

import base64
import json
import logging
import shutil
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydaw.model.project import (
    Clip,
    MediaItem,
    Track,
    new_id,
)
from pydaw.model.midi import MidiNote

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes for intermediate DAWproject representation
# ---------------------------------------------------------------------------

@dataclass
class DawProjectMetadata:
    title: str = ""
    artist: str = ""
    comment: str = ""
    application: str = ""
    app_version: str = ""


@dataclass
class DawProjectNote:
    """A single note from a DAWproject Notes lane."""
    time: float = 0.0       # beats
    duration: float = 1.0   # beats
    channel: int = 0
    key: int = 60           # MIDI pitch
    velocity: float = 0.8   # 0..1 normalized
    release_velocity: float = 0.0
    # v0.0.20.658: Per-note expressions
    expressions: Dict[str, List[Dict[str, float]]] = field(default_factory=dict)


@dataclass
class DawProjectAutomationPoint:
    """A single automation breakpoint."""
    time: float = 0.0
    value: float = 0.0
    interpolation: str = "linear"  # linear | hold | bezier
    bezier_cx: float = 0.5
    bezier_cy: float = 0.5


@dataclass
class DawProjectAutomationLane:
    """An automation lane for a parameter on a track."""
    parameter_id: str = ""
    name: str = ""
    enabled: bool = True
    color: str = "#00BFFF"
    points: List[DawProjectAutomationPoint] = field(default_factory=list)


@dataclass
class DawProjectSend:
    """A send routing from a track to an FX return track."""
    destination_track_id: str = ""
    amount: float = 0.5
    pre_fader: bool = False


@dataclass
class DawProjectDevice:
    """A plugin device parsed from the Structure."""
    name: str = ""
    device_id: str = ""
    role: str = ""       # "instrument" | "audio-fx" | "note-fx"
    enabled: bool = True
    format: str = ""     # "VST3" | "CLAP" | "LV2" | "INTERNAL"
    state_blob: str = ""  # Base64-encoded state
    state_path: str = ""  # path inside archive
    parameters: Dict[str, str] = field(default_factory=dict)


@dataclass
class DawProjectClip:
    """A clip inside a DAWproject Arrangement lane."""
    time: float = 0.0          # beats (position on timeline)
    duration: float = 4.0      # beats
    content_time_offset: float = 0.0
    name: str = ""
    color: str = ""
    muted: bool = False
    reversed: bool = False
    group_id: str = ""
    # For audio clips
    audio_file: str = ""       # relative path inside the archive
    # For note clips
    notes: List[DawProjectNote] = field(default_factory=list)
    # v0.0.20.658: Clip extensions (ChronoScaleStudio or compatible)
    gain: float = 1.0
    pan: float = 0.0
    pitch: float = 0.0
    stretch: float = 1.0
    clip_automation: Dict[str, List[Dict[str, float]]] = field(default_factory=dict)


@dataclass
class DawProjectTrack:
    """Parsed track from DAWproject Structure."""
    id: str = ""
    name: str = ""
    color: str = ""
    content_type: str = ""     # "notes", "audio", "automationLanes", ...
    role: str = ""             # "track", "master", "effect", "group"
    pydaw_kind: str = ""       # ChronoScaleStudio extension: original track kind
    volume: float = 0.8        # linear 0..2
    pan: float = 0.5           # normalized 0..1 (0.5 = center)
    mute: bool = False
    solo: bool = False
    # Group hierarchy
    group_id: str = ""         # parent group track ID
    group_name: str = ""       # parent group name
    # Clips from the Arrangement that belong to this track
    clips: List[DawProjectClip] = field(default_factory=list)
    # Plugin devices
    devices: List[DawProjectDevice] = field(default_factory=list)
    # Send routing
    sends: List[DawProjectSend] = field(default_factory=list)
    # Automation lanes
    automation_lanes: List[DawProjectAutomationLane] = field(default_factory=list)
    # Channel config
    channel_config: str = ""   # "mono" | "stereo"


@dataclass
class DawProjectData:
    """Complete parsed DAWproject."""
    metadata: DawProjectMetadata = field(default_factory=DawProjectMetadata)
    bpm: float = 120.0
    time_sig_num: int = 4
    time_sig_den: int = 4
    tracks: List[DawProjectTrack] = field(default_factory=list)
    # All audio file paths found inside the archive
    audio_files: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# XML Parsing helpers
# ---------------------------------------------------------------------------

def _attr_float(elem: ET.Element, name: str, default: float = 0.0) -> float:
    try:
        return float(elem.get(name, default))
    except (ValueError, TypeError):
        return default


def _attr_int(elem: ET.Element, name: str, default: int = 0) -> int:
    try:
        return int(elem.get(name, default))
    except (ValueError, TypeError):
        return default


def _attr_bool(elem: ET.Element, name: str, default: bool = False) -> bool:
    val = elem.get(name, "")
    if val.lower() in ("true", "1", "yes"):
        return True
    if val.lower() in ("false", "0", "no"):
        return False
    return default


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

class DawProjectParser:
    """Parse a .dawproject ZIP archive into DawProjectData."""

    def __init__(self, path: Path):
        self.path = path
        self._track_map: Dict[str, DawProjectTrack] = {}  # id -> track
        self._archive_names: List[str] = []

    def parse(self) -> DawProjectData:
        """Parse the .dawproject file and return structured data."""
        data = DawProjectData()

        if not self.path.exists():
            raise FileNotFoundError(f"File not found: {self.path}")

        if not zipfile.is_zipfile(self.path):
            raise ValueError(f"Not a valid ZIP archive: {self.path}")

        with zipfile.ZipFile(self.path, 'r') as zf:
            names = zf.namelist()
            self._archive_names = names

            # Parse metadata.xml (optional)
            meta_name = self._find_file(names, "metadata.xml")
            if meta_name:
                try:
                    with zf.open(meta_name) as f:
                        data.metadata = self._parse_metadata(ET.parse(f).getroot())
                except Exception as e:
                    log.warning("Failed to parse metadata.xml: %s", e)

            # Parse project.xml (required)
            proj_name = self._find_file(names, "project.xml")
            if not proj_name:
                raise ValueError("project.xml not found in .dawproject archive")

            with zf.open(proj_name) as f:
                root = ET.parse(f).getroot()

            self._parse_project(root, data)

            # Collect audio file paths
            for name in names:
                lower = name.lower()
                if any(lower.endswith(ext) for ext in ('.wav', '.flac', '.ogg', '.mp3', '.aiff', '.aif')):
                    data.audio_files.append(name)

            # v0.0.20.658: Load inline plugin state blobs from archive
            self._load_state_files(zf, data)

        return data

    @staticmethod
    def _find_file(names: List[str], filename: str) -> Optional[str]:
        """Find a file in ZIP, accounting for possible subdirectory prefix."""
        for n in names:
            if n.endswith(filename) and (n == filename or n.endswith('/' + filename)):
                return n
        return None

    def _parse_metadata(self, root: ET.Element) -> DawProjectMetadata:
        meta = DawProjectMetadata()
        meta.title = root.findtext("Title", "")
        meta.artist = root.findtext("Artist", "")
        meta.comment = root.findtext("Comment", "")
        meta.application = root.findtext("Application", "")
        meta.app_version = root.findtext("ApplicationVersion", "")
        return meta

    def _parse_project(self, root: ET.Element, data: DawProjectData) -> None:
        """Parse the <Project> root element."""
        # Application info
        app = root.find("Application")
        if app is not None:
            data.metadata.application = app.get("name", "") or data.metadata.application
            data.metadata.app_version = app.get("version", "") or data.metadata.app_version

        # Transport: BPM + TimeSignature
        transport = root.find("Transport")
        if transport is not None:
            tempo = transport.find("Tempo")
            if tempo is not None:
                data.bpm = _attr_float(tempo, "value", 120.0)

            ts = transport.find("TimeSignature")
            if ts is not None:
                data.time_sig_num = _attr_int(ts, "numerator", 4)
                data.time_sig_den = _attr_int(ts, "denominator", 4)

        # Structure: Tracks
        structure = root.find("Structure")
        if structure is not None:
            self._parse_structure(structure, data)

        # Arrangement: Clips + Automation mapped to tracks
        arrangement = root.find("Arrangement")
        if arrangement is not None:
            self._parse_arrangement(arrangement, data)

    def _parse_structure(self, structure: ET.Element, data: DawProjectData) -> None:
        """Parse <Structure> containing <Track> elements."""
        for track_elem in structure.iter("Track"):
            trk = DawProjectTrack()
            trk.id = track_elem.get("id", "")
            trk.name = track_elem.get("name", "Track")
            trk.color = track_elem.get("color", "")
            trk.content_type = track_elem.get("contentType", "")
            trk.role = track_elem.get("role", "track")
            trk.pydaw_kind = track_elem.get("pydawKind", "")
            trk.group_id = track_elem.get("groupId", "")
            trk.group_name = track_elem.get("groupName", "")

            # Channel info
            channel = track_elem.find("Channel")
            if channel is not None:
                vol = channel.find("Volume")
                if vol is not None:
                    trk.volume = _attr_float(vol, "value", 0.8)

                pan = channel.find("Pan")
                if pan is not None:
                    trk.pan = _attr_float(pan, "value", 0.5)

                mute = channel.find("Mute")
                if mute is not None:
                    trk.mute = _attr_bool(mute, "value", False)

                solo = channel.find("Solo")
                if solo is not None:
                    trk.solo = _attr_bool(solo, "value", False)

                # v0.0.20.658: Parse Sends
                sends_elem = channel.find("Sends")
                if sends_elem is not None:
                    for send_elem in sends_elem:
                        if send_elem.tag == "Send":
                            send = DawProjectSend(
                                destination_track_id=send_elem.get("destination", ""),
                                amount=_attr_float(send_elem, "volume", 0.5),
                                pre_fader=_attr_bool(send_elem, "preFader", False),
                            )
                            trk.sends.append(send)

                # v0.0.20.658: Parse Devices (plugins)
                devices = channel.find("Devices")
                if devices is not None:
                    for dev_elem in devices:
                        tag = dev_elem.tag
                        if "Plugin" in tag:
                            dev = self._parse_device(dev_elem)
                            trk.devices.append(dev)
                        elif tag == "DeviceChain":
                            chain_role = dev_elem.get("role", "audio-fx")
                            for sub_dev in dev_elem:
                                if "Plugin" in sub_dev.tag:
                                    dev = self._parse_device(sub_dev)
                                    if not dev.role:
                                        dev.role = chain_role
                                    trk.devices.append(dev)

            data.tracks.append(trk)
            self._track_map[trk.id] = trk

    def _parse_device(self, dev_elem: ET.Element) -> DawProjectDevice:
        """Parse a single <Plugin> element into a DawProjectDevice."""
        dev = DawProjectDevice()
        dev.name = dev_elem.get("deviceName", dev_elem.get("name", ""))
        dev.device_id = dev_elem.get("deviceID", "")
        dev.role = dev_elem.get("role", "")
        dev.enabled = _attr_bool(dev_elem, "enabled", True)
        dev.format = dev_elem.get("format", "")

        # State blob (inline Base64)
        state_elem = dev_elem.find("State")
        if state_elem is not None:
            if state_elem.text and state_elem.text.strip():
                dev.state_blob = state_elem.text.strip()
            state_path = state_elem.get("path", "")
            if state_path:
                dev.state_path = state_path

        # Parameters
        params_elem = dev_elem.find("Parameters")
        if params_elem is not None:
            for param_elem in params_elem:
                if param_elem.tag == "Parameter":
                    pid = param_elem.get("id", "")
                    pval = param_elem.get("value", "")
                    if pid:
                        dev.parameters[pid] = pval

        return dev

    def _parse_arrangement(self, arrangement: ET.Element, data: DawProjectData) -> None:
        """Parse <Arrangement> → <Lanes> → clips + automation."""
        self._walk_lanes(arrangement, track_id=None)

    def _walk_lanes(self, parent: ET.Element, track_id: Optional[str]) -> None:
        """Recursively walk <Lanes> elements to find clips and automation."""
        for child in parent:
            tag = child.tag

            if tag == "Lanes":
                tid = child.get("track", track_id)
                self._walk_lanes(child, tid)

            elif tag == "Clips":
                self._parse_clips(child, track_id)

            elif tag == "Clip":
                self._parse_single_clip(child, track_id)

            elif tag == "AutomationLanes":
                self._parse_automation_lanes(child, track_id)

            elif tag == "AutomationLane":
                self._parse_single_automation_lane(child, track_id)

    def _parse_clips(self, clips_elem: ET.Element, track_id: Optional[str]) -> None:
        """Parse a <Clips> container."""
        for clip_elem in clips_elem:
            if clip_elem.tag == "Clip":
                self._parse_single_clip(clip_elem, track_id)

    def _parse_single_clip(self, clip_elem: ET.Element, track_id: Optional[str]) -> None:
        """Parse a single <Clip> element."""
        clip = DawProjectClip()
        clip.time = _attr_float(clip_elem, "time", 0.0)
        clip.duration = _attr_float(clip_elem, "duration", 4.0)
        clip.content_time_offset = _attr_float(clip_elem, "contentTimeOffset", 0.0)
        clip.name = clip_elem.get("name", "")
        clip.color = clip_elem.get("color", "")
        clip.muted = _attr_bool(clip_elem, "muted", False)
        clip.reversed = _attr_bool(clip_elem, "reversed", False)
        clip.group_id = clip_elem.get("groupId", "")

        # Check for <Notes> content
        notes_elem = clip_elem.find("Notes")
        if notes_elem is not None:
            for note_elem in notes_elem.iter("Note"):
                note = DawProjectNote(
                    time=_attr_float(note_elem, "time", 0.0),
                    duration=_attr_float(note_elem, "duration", 1.0),
                    channel=_attr_int(note_elem, "channel", 0),
                    key=_attr_int(note_elem, "key", 60),
                    velocity=_attr_float(note_elem, "vel", 0.8),
                    release_velocity=_attr_float(note_elem, "rel", 0.0),
                )
                # Per-note expressions
                exprs_elem = note_elem.find("NoteExpressions")
                if exprs_elem is not None:
                    for expr_elem in exprs_elem:
                        if expr_elem.tag == "Expression":
                            expr_id = expr_elem.get("id", "")
                            points = []
                            for pt in expr_elem:
                                if pt.tag == "Point":
                                    points.append({
                                        "t": _attr_float(pt, "t", 0.0),
                                        "v": _attr_float(pt, "v", 0.0),
                                    })
                            if expr_id and points:
                                note.expressions[expr_id] = points
                clip.notes.append(note)

        # Check for <Audio> content (file reference)
        audio_elem = clip_elem.find("Audio")
        if audio_elem is not None:
            file_elem = audio_elem.find("File")
            if file_elem is not None:
                clip.audio_file = file_elem.get("path", "")

        # Also check for direct <File> reference (some exporters)
        if not clip.audio_file:
            file_direct = clip_elem.find("File")
            if file_direct is not None:
                clip.audio_file = file_direct.get("path", "")

        # v0.0.20.658: Parse Extensions (ChronoScaleStudio or compatible)
        ext_elem = clip_elem.find("Extensions")
        if ext_elem is not None:
            for tag_name, attr_name in [("Gain", "gain"), ("Pan", "pan"),
                                         ("Pitch", "pitch"), ("Stretch", "stretch")]:
                sub = ext_elem.find(tag_name)
                if sub is not None:
                    try:
                        setattr(clip, attr_name, float(sub.get("value", getattr(clip, attr_name))))
                    except (ValueError, TypeError):
                        pass
            # Clip automation from extensions
            clip_auto_elem = ext_elem.find("ClipAutomation")
            if clip_auto_elem is not None:
                for lane_elem in clip_auto_elem:
                    if lane_elem.tag == "Lane":
                        lane_id = lane_elem.get("id", "")
                        points = []
                        for pt in lane_elem:
                            if pt.tag == "Point":
                                try:
                                    points.append({
                                        "beat": float(pt.get("beat", "0.0")),
                                        "value": float(pt.get("value", "0.0")),
                                    })
                                except (ValueError, TypeError):
                                    pass
                        if lane_id and points:
                            clip.clip_automation[lane_id] = points

        # Assign to track
        if track_id and track_id in self._track_map:
            self._track_map[track_id].clips.append(clip)
        else:
            log.debug("Clip '%s' has no track mapping (track_id=%s)", clip.name, track_id)

    def _parse_automation_lanes(self, auto_elem: ET.Element, track_id: Optional[str]) -> None:
        """Parse an <AutomationLanes> container."""
        for lane_elem in auto_elem:
            if lane_elem.tag == "AutomationLane":
                self._parse_single_automation_lane(lane_elem, track_id)

    def _parse_single_automation_lane(self, lane_elem: ET.Element, track_id: Optional[str]) -> None:
        """Parse a single <AutomationLane> element."""
        lane = DawProjectAutomationLane()
        lane.parameter_id = lane_elem.get("parameterID", lane_elem.get("parameter", ""))
        lane.name = lane_elem.get("name", lane.parameter_id)
        lane.enabled = _attr_bool(lane_elem, "enabled", True)
        lane.color = lane_elem.get("color", "#00BFFF")

        points_elem = lane_elem.find("Points")
        if points_elem is not None:
            for pt in points_elem:
                if pt.tag == "Point":
                    point = DawProjectAutomationPoint(
                        time=_attr_float(pt, "time", 0.0),
                        value=_attr_float(pt, "value", 0.0),
                        interpolation=pt.get("interpolation", "linear"),
                    )
                    if pt.get("bezierCx"):
                        try:
                            point.bezier_cx = float(pt.get("bezierCx", "0.5"))
                        except (ValueError, TypeError):
                            pass
                    if pt.get("bezierCy"):
                        try:
                            point.bezier_cy = float(pt.get("bezierCy", "0.5"))
                        except (ValueError, TypeError):
                            pass
                    lane.points.append(point)

        if track_id and track_id in self._track_map:
            self._track_map[track_id].automation_lanes.append(lane)
        else:
            log.debug("AutomationLane '%s' has no track mapping (track_id=%s)",
                      lane.name, track_id)

    def _load_state_files(self, zf: zipfile.ZipFile, data: DawProjectData) -> None:
        """Load plugin state files from the archive for devices with state_path."""
        for track in data.tracks:
            for dev in track.devices:
                if dev.state_path and not dev.state_blob:
                    try:
                        if dev.state_path in zf.namelist():
                            raw = zf.read(dev.state_path)
                            dev.state_blob = base64.b64encode(raw).decode("ascii")
                    except Exception as e:
                        log.warning("Failed to load plugin state %s: %s",
                                    dev.state_path, e)


# ---------------------------------------------------------------------------
# Importer: Maps DawProjectData → PyDAW Project modifications
# ---------------------------------------------------------------------------

@dataclass
class ImportResult:
    """Summary of what was imported."""
    tracks_created: int = 0
    clips_created: int = 0
    notes_imported: int = 0
    audio_files_copied: int = 0
    automation_lanes_imported: int = 0
    plugin_states_imported: int = 0
    sends_imported: int = 0
    warnings: List[str] = field(default_factory=list)
    source_app: str = ""
    project_name: str = ""


class DawProjectImporter:
    """Import a parsed DawProjectData into an existing PyDAW project.

    This is designed to be non-destructive:
    - New tracks and clips are ADDED (existing content is untouched)
    - BPM/time signature are only updated if the project is empty or user opts in
    """

    def __init__(
        self,
        dawproject_path: Path,
        project,   # pydaw.model.project.Project
        media_dir: Path,
        update_transport: bool = True,
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ):
        self.dawproject_path = dawproject_path
        self.project = project
        self.media_dir = media_dir
        self.update_transport = update_transport
        self.progress_cb = progress_cb or (lambda pct, msg: None)
        # Maps: original dawproject track ID → new PyDAW track ID
        self._track_id_map: Dict[str, str] = {}

    def run(self) -> ImportResult:
        """Execute the full import pipeline. Returns ImportResult."""
        result = ImportResult()

        # Step 1: Parse .dawproject
        self.progress_cb(5, "Parsing .dawproject …")
        parser = DawProjectParser(self.dawproject_path)
        data = parser.parse()

        result.source_app = f"{data.metadata.application} {data.metadata.app_version}".strip()
        result.project_name = data.metadata.title or self.dawproject_path.stem

        # Step 2: Update transport (BPM, time signature)
        if self.update_transport:
            self.progress_cb(10, "Transport-Einstellungen übernehmen …")
            self._apply_transport(data)

        # Step 3: Extract audio files
        self.progress_cb(15, "Audio-Dateien extrahieren …")
        audio_map = self._extract_audio_files(data, result)

        # Step 4: Create tracks + clips + notes + sends + plugin states
        self.progress_cb(30, "Spuren und Clips erstellen …")
        self._create_tracks_and_clips(data, audio_map, result)

        # Step 5: Import automation lanes
        self.progress_cb(85, "Automation importieren …")
        self._import_automation(data, result)

        self.progress_cb(100, "Import abgeschlossen!")
        return result

    def _apply_transport(self, data: DawProjectData) -> None:
        """Apply BPM and time signature from the dawproject."""
        if data.bpm > 0:
            self.project.bpm = data.bpm
        if data.time_sig_num > 0 and data.time_sig_den > 0:
            self.project.time_signature = f"{data.time_sig_num}/{data.time_sig_den}"

    def _extract_audio_files(
        self, data: DawProjectData, result: ImportResult
    ) -> Dict[str, Path]:
        """Extract audio files from the archive into the project's media dir."""
        audio_map: Dict[str, Path] = {}
        if not data.audio_files:
            return audio_map

        self.media_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(self.dawproject_path, 'r') as zf:
                total = len(data.audio_files)
                for i, arc_path in enumerate(data.audio_files):
                    try:
                        pct = 15 + int(15 * (i / max(total, 1)))
                        fname = Path(arc_path).name
                        self.progress_cb(pct, f"Audio: {fname}")

                        dest = self.media_dir / fname
                        if dest.exists():
                            stem, suffix = dest.stem, dest.suffix
                            counter = 1
                            while dest.exists():
                                dest = self.media_dir / f"{stem}_{counter}{suffix}"
                                counter += 1

                        with zf.open(arc_path) as src, open(dest, 'wb') as dst:
                            shutil.copyfileobj(src, dst)

                        audio_map[arc_path] = dest
                        result.audio_files_copied += 1
                    except Exception as e:
                        msg = f"Audio-Extraktion fehlgeschlagen: {arc_path}: {e}"
                        log.warning(msg)
                        result.warnings.append(msg)
        except Exception as e:
            log.error("Failed to open ZIP for audio extraction: %s", e)

        return audio_map

    def _create_tracks_and_clips(
        self, data: DawProjectData, audio_map: Dict[str, Path], result: ImportResult
    ) -> None:
        """Create PyDAW tracks and clips from parsed DAWproject data."""
        total = len(data.tracks)

        for i, daw_track in enumerate(data.tracks):
            pct = 30 + int(50 * (i / max(total, 1)))
            self.progress_cb(pct, f"Track: {daw_track.name}")

            # Skip master (map to existing)
            if daw_track.role == "master":
                master = next((t for t in self.project.tracks if t.kind == "master"), None)
                if master:
                    self._track_id_map[daw_track.id] = master.id
                continue

            kind = self._determine_track_kind(daw_track)

            trk = Track(
                kind=kind,
                name=daw_track.name or f"Imported Track {i + 1}",
                volume=self._convert_volume(daw_track.volume),
                pan=self._convert_pan(daw_track.pan),
                muted=daw_track.mute,
                solo=daw_track.solo,
            )

            # Group hierarchy
            if daw_track.group_id:
                mapped_group = self._track_id_map.get(daw_track.group_id, "")
                trk.track_group_id = mapped_group
                trk.track_group_name = daw_track.group_name

            # Channel config
            if daw_track.channel_config:
                trk.channel_config = daw_track.channel_config

            # Import plugin devices
            self._apply_devices(trk, daw_track, result)

            # Store ID mapping
            self._track_id_map[daw_track.id] = trk.id

            # Insert before master track
            tracks = [t for t in self.project.tracks if t.kind != "master"]
            master = next((t for t in self.project.tracks if t.kind == "master"), None)
            tracks.append(trk)
            if master:
                tracks.append(master)
            self.project.tracks = tracks
            result.tracks_created += 1

            # Create clips
            for clip_data in daw_track.clips:
                if clip_data.notes:
                    self._create_midi_clip(trk, clip_data, result)
                elif clip_data.audio_file:
                    self._create_audio_clip(trk, clip_data, audio_map, result)

        # Resolve sends (all tracks exist now)
        self._resolve_sends(data, result)

    def _determine_track_kind(self, daw_track: DawProjectTrack) -> str:
        """Determine PyDAW track kind from DAWproject data."""
        if daw_track.pydaw_kind:
            return daw_track.pydaw_kind

        role = daw_track.role.lower()
        if role in ("effect", "fx"):
            return "fx"
        if role in ("group", "folder"):
            return "group"
        if role == "master":
            return "master"

        has_notes = any(c.notes for c in daw_track.clips)
        has_instrument = any(d.role == "instrument" for d in daw_track.devices)
        content_type = daw_track.content_type.lower()

        if content_type == "notes" or has_notes or has_instrument:
            return "instrument"
        if content_type == "audio" or any(c.audio_file for c in daw_track.clips):
            return "audio"
        return "audio"

    def _apply_devices(self, trk: Track, daw_track: DawProjectTrack,
                       result: ImportResult) -> None:
        """Apply parsed plugin devices to a PyDAW track."""
        try:
            from pydaw.fileio.dawproject_plugin_map import dawproject_device_id_to_pydaw_id
        except ImportError:
            def dawproject_device_id_to_pydaw_id(x):
                return None

        for dev in daw_track.devices:
            role = dev.role.lower() if dev.role else ""

            if role == "instrument":
                pydaw_id = dawproject_device_id_to_pydaw_id(dev.device_id)
                if pydaw_id:
                    trk.plugin_type = pydaw_id
                else:
                    trk.plugin_type = dev.device_id or dev.name
                trk.instrument_enabled = dev.enabled

                state = self._decode_state(dev)
                if state is not None:
                    if isinstance(state, dict):
                        trk.instrument_state = state
                    else:
                        trk.instrument_state = {"__ext_state_b64": dev.state_blob}
                    result.plugin_states_imported += 1

            elif role in ("audio-fx", "note-fx"):
                chain_key = "note_fx_chain" if role == "note-fx" else "audio_fx_chain"
                chain = getattr(trk, chain_key, {})
                if not isinstance(chain, dict):
                    chain = {"devices": []}
                devices_list = chain.get("devices", [])
                if not isinstance(devices_list, list):
                    devices_list = []

                pydaw_id = dawproject_device_id_to_pydaw_id(dev.device_id)
                device_dict: Dict[str, Any] = {
                    "plugin_id": pydaw_id or dev.device_id or dev.name,
                    "name": dev.name,
                    "enabled": dev.enabled,
                    "params": {k: self._try_parse_number(v)
                               for k, v in dev.parameters.items()},
                }
                state = self._decode_state(dev)
                if state is not None:
                    if isinstance(state, dict):
                        device_dict["plugin_state"] = state
                    else:
                        device_dict["plugin_state"] = {"__ext_state_b64": dev.state_blob}
                    result.plugin_states_imported += 1

                devices_list.append(device_dict)
                chain["devices"] = devices_list
                setattr(trk, chain_key, chain)

    def _decode_state(self, dev: DawProjectDevice) -> Optional[Any]:
        """Try to decode a plugin state blob."""
        if not dev.state_blob:
            return None
        try:
            raw = base64.b64decode(dev.state_blob)
            try:
                return json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
            return {"__raw_state": True, "__ext_state_b64": dev.state_blob}
        except Exception:
            return None

    def _resolve_sends(self, data: DawProjectData, result: ImportResult) -> None:
        """Resolve send routing after all tracks have been created."""
        for daw_track in data.tracks:
            if not daw_track.sends:
                continue
            new_track_id = self._track_id_map.get(daw_track.id, "")
            if not new_track_id:
                continue
            trk = next((t for t in self.project.tracks if t.id == new_track_id), None)
            if trk is None:
                continue
            for send in daw_track.sends:
                dest_id = self._track_id_map.get(send.destination_track_id, "")
                if dest_id:
                    trk.sends.append({
                        "target_track_id": dest_id,
                        "amount": send.amount,
                        "pre_fader": send.pre_fader,
                    })
                    result.sends_imported += 1
                else:
                    result.warnings.append(
                        f"Send destination '{send.destination_track_id}' "
                        f"nicht gefunden (Track: {daw_track.name})"
                    )

    def _import_automation(self, data: DawProjectData, result: ImportResult) -> None:
        """Import automation lanes into project.automation_manager_lanes."""
        if not hasattr(self.project, "automation_manager_lanes"):
            return
        if not isinstance(self.project.automation_manager_lanes, dict):
            self.project.automation_manager_lanes = {}

        for daw_track in data.tracks:
            new_track_id = self._track_id_map.get(daw_track.id, "")
            if not new_track_id:
                continue

            for lane in daw_track.automation_lanes:
                param_key = (f"{new_track_id}:{lane.parameter_id}"
                             if lane.parameter_id
                             else f"{new_track_id}:auto_{new_id('lane')}")

                points = []
                for pt in lane.points:
                    point_dict: Dict[str, Any] = {
                        "beat": pt.time,
                        "value": pt.value,
                        "curve_type": pt.interpolation,
                    }
                    if pt.interpolation == "bezier":
                        point_dict["bezier_cx"] = pt.bezier_cx
                        point_dict["bezier_cy"] = pt.bezier_cy
                    points.append(point_dict)

                lane_dict: Dict[str, Any] = {
                    "track_id": new_track_id,
                    "param_name": lane.name or lane.parameter_id,
                    "enabled": lane.enabled,
                    "color": lane.color,
                    "points": points,
                }

                self.project.automation_manager_lanes[param_key] = lane_dict
                result.automation_lanes_imported += 1

    def _create_midi_clip(self, trk: Track, clip_data: DawProjectClip,
                          result: ImportResult) -> None:
        """Create a MIDI clip with notes."""
        clip = Clip(
            kind="midi",
            track_id=trk.id,
            start_beats=clip_data.time,
            length_beats=max(clip_data.duration, 1.0),
            label=clip_data.name or "Imported Clip",
            muted=clip_data.muted,
            reversed=clip_data.reversed,
            group_id=clip_data.group_id,
            gain=clip_data.gain,
            pan=clip_data.pan,
            pitch=clip_data.pitch,
            stretch=clip_data.stretch,
            clip_automation=clip_data.clip_automation,
        )
        self.project.clips.append(clip)
        result.clips_created += 1

        notes = []
        for dn in clip_data.notes:
            vel = max(1, min(127, int(dn.velocity * 127)))
            note = MidiNote(
                pitch=max(0, min(127, dn.key)),
                start_beats=max(0.0, dn.time - clip_data.content_time_offset),
                length_beats=max(0.0625, dn.duration),
                velocity=vel,
            ).clamp()
            if dn.expressions:
                note.expressions = dn.expressions
            notes.append(note)
            result.notes_imported += 1

        if notes:
            self.project.midi_notes[clip.id] = notes

    def _create_audio_clip(self, trk: Track, clip_data: DawProjectClip,
                           audio_map: Dict[str, Path], result: ImportResult) -> None:
        """Create an audio clip referencing an extracted audio file."""
        local_path: Optional[Path] = None

        if clip_data.audio_file in audio_map:
            local_path = audio_map[clip_data.audio_file]
        else:
            target_name = Path(clip_data.audio_file).name.lower()
            for arc_path, loc_path in audio_map.items():
                if Path(arc_path).name.lower() == target_name:
                    local_path = loc_path
                    break

        source_path = str(local_path) if local_path else ""

        media_id = ""
        if local_path and local_path.exists():
            mi = MediaItem(
                kind="audio",
                path=str(local_path),
                label=local_path.name,
            )
            self.project.media.append(mi)
            media_id = mi.id

        clip = Clip(
            kind="audio",
            track_id=trk.id,
            start_beats=clip_data.time,
            length_beats=max(clip_data.duration, 1.0),
            offset_beats=clip_data.content_time_offset,
            label=clip_data.name or (Path(clip_data.audio_file).stem
                                      if clip_data.audio_file else "Audio Clip"),
            source_path=source_path,
            media_id=media_id,
            muted=clip_data.muted,
            reversed=clip_data.reversed,
            group_id=clip_data.group_id,
            gain=clip_data.gain,
            pan=clip_data.pan,
            pitch=clip_data.pitch,
            stretch=clip_data.stretch,
            clip_automation=clip_data.clip_automation,
        )
        self.project.clips.append(clip)
        result.clips_created += 1

    # --- Conversion helpers ---

    @staticmethod
    def _convert_volume(dawproject_volume: float) -> float:
        """Convert DAWproject volume (linear 0..2) to PyDAW volume (0..1)."""
        return max(0.0, min(1.0, dawproject_volume * 0.8))

    @staticmethod
    def _convert_pan(dawproject_pan: float) -> float:
        """Convert DAWproject pan (0..1, 0.5=center) to PyDAW pan (-1..+1, 0=center)."""
        return max(-1.0, min(1.0, (dawproject_pan - 0.5) * 2.0))

    @staticmethod
    def _try_parse_number(val: str) -> Any:
        """Try to parse a string as number, fall back to string."""
        try:
            f = float(val)
            if f == int(f) and "." not in val:
                return int(f)
            return f
        except (ValueError, TypeError):
            return val


# ---------------------------------------------------------------------------
# Convenience function for UI integration
# ---------------------------------------------------------------------------

def import_dawproject(
    dawproject_path: Path,
    project,
    media_dir: Path,
    update_transport: bool = True,
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> ImportResult:
    """High-level entry point for importing a .dawproject file."""
    importer = DawProjectImporter(
        dawproject_path=dawproject_path,
        project=project,
        media_dir=media_dir,
        update_transport=update_transport,
        progress_cb=progress_cb,
    )
    return importer.run()
