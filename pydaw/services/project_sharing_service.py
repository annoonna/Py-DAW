"""Project Sharing Service — Shareable project packages.

Creates self-contained, portable project packages that can be shared
between users. A shared package is a ZIP archive containing:

  project_name.pydaw-share/
  ├── project.json           ← Full project state
  ├── metadata.json          ← Sharing metadata (author, created, description)
  ├── media/                 ← All referenced audio files (embedded)
  │   ├── kick.wav
  │   └── vocal_take1.wav
  ├── plugins/               ← Plugin state snapshots (Base64 blobs)
  ├── thumbnail.png          ← Optional waveform/arrangement thumbnail
  └── README.txt             ← Human-readable project info

Features:
  - Collect + embed all referenced audio files (resolve relative paths)
  - Embed plugin state blobs inline (no external dependencies)
  - Generate human-readable README with project stats
  - Import shared packages into existing projects (merge or replace)
  - Configurable: include/exclude media, strip personal data
  - Progress callbacks for UI integration

v0.0.20.658 — AP10 Phase 10D (Claude Opus 4.6, 2026-03-20)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from pydaw.version import __version__

log = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ShareMetadata:
    """Metadata embedded in a shared project package."""
    project_name: str = ""
    author: str = ""
    description: str = ""
    created_utc: str = ""
    app_version: str = ""
    bpm: float = 120.0
    time_signature: str = "4/4"
    tracks_count: int = 0
    clips_count: int = 0
    media_files_count: int = 0
    total_duration_beats: float = 0.0
    content_hash: str = ""
    share_format_version: str = "1.0"
    # Tags for search/discovery
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ShareMetadata":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class ShareExportConfig:
    """Configuration for creating a shared package."""
    include_media: bool = True
    include_plugin_states: bool = True
    strip_personal_data: bool = False      # remove author info, file paths
    compress_level: int = 6                # ZIP compression 0-9
    max_media_size_mb: float = 500.0       # skip media files larger than this
    author: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class ShareExportResult:
    """Result of creating a shared package."""
    output_path: Path = field(default_factory=lambda: Path("."))
    package_size_bytes: int = 0
    media_files_included: int = 0
    media_files_skipped: int = 0
    plugin_states_included: int = 0
    content_hash: str = ""
    warnings: List[str] = field(default_factory=list)


@dataclass
class ShareImportResult:
    """Result of importing a shared package."""
    project_name: str = ""
    source_author: str = ""
    tracks_imported: int = 0
    clips_imported: int = 0
    media_files_extracted: int = 0
    plugin_states_restored: int = 0
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Export: Create shareable package
# ---------------------------------------------------------------------------

class ProjectShareExporter:
    """Create a self-contained shareable project package."""

    SHARE_EXTENSION = ".pydaw-share"

    def __init__(
        self,
        project,
        project_root: Optional[Path] = None,
        config: Optional[ShareExportConfig] = None,
        progress_cb: Optional[ProgressCallback] = None,
    ):
        self.project = project
        self.project_root = Path(project_root) if project_root else None
        self.config = config or ShareExportConfig()
        self.progress_cb: ProgressCallback = progress_cb or (lambda pct, msg: None)

    def export(self, target_path: Path) -> ShareExportResult:
        """Create the shareable package at target_path."""
        out_path = Path(target_path)
        if not str(out_path).endswith(self.SHARE_EXTENSION):
            out_path = out_path.with_suffix(self.SHARE_EXTENSION)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        result = ShareExportResult(output_path=out_path)

        sibling_tmp: Optional[Path] = None
        try:
            with tempfile.TemporaryDirectory(prefix="pydaw_share_") as tmp_dir:
                staging = Path(tmp_dir) / "stage"
                staging.mkdir()
                (staging / "media").mkdir()
                (staging / "plugins").mkdir()

                # 1. Serialize project
                self.progress_cb(5, "Projekt serialisieren …")
                proj_dict = self._serialize_project()

                # 2. Collect media files
                if self.config.include_media:
                    self.progress_cb(15, "Audio-Dateien sammeln …")
                    self._collect_media(staging, proj_dict, result)

                # 3. Strip personal data if requested
                if self.config.strip_personal_data:
                    self._strip_personal_data(proj_dict)

                # 4. Write project.json
                self.progress_cb(60, "Projekt-Daten schreiben …")
                proj_json = json.dumps(proj_dict, ensure_ascii=False, sort_keys=True, indent=2)
                (staging / "project.json").write_text(proj_json, encoding="utf-8")

                content_hash = hashlib.sha256(proj_json.encode("utf-8")).hexdigest()[:16]
                result.content_hash = content_hash

                # 5. Write metadata.json
                self.progress_cb(70, "Metadaten erstellen …")
                metadata = self._build_metadata(proj_dict, result, content_hash)
                (staging / "metadata.json").write_text(
                    json.dumps(metadata.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                # 6. Write README.txt
                self.progress_cb(75, "README erstellen …")
                readme = self._build_readme(metadata, result)
                (staging / "README.txt").write_text(readme, encoding="utf-8")

                # 7. Build ZIP
                self.progress_cb(80, "Paket erstellen …")
                with tempfile.NamedTemporaryFile(
                    prefix=f".{out_path.stem}_",
                    suffix=".tmp",
                    dir=str(out_path.parent),
                    delete=False,
                ) as tmp_file:
                    sibling_tmp = Path(tmp_file.name)

                with zipfile.ZipFile(sibling_tmp, "w",
                                     compression=zipfile.ZIP_DEFLATED,
                                     compresslevel=self.config.compress_level) as zf:
                    for fpath in sorted(staging.rglob("*")):
                        if fpath.is_file():
                            arcname = fpath.relative_to(staging).as_posix()
                            zf.write(fpath, arcname)

                result.package_size_bytes = sibling_tmp.stat().st_size

                # 8. Validate + move
                self.progress_cb(95, "Paket validieren …")
                self._validate_package(sibling_tmp)
                os.replace(sibling_tmp, out_path)
                sibling_tmp = None

        finally:
            if sibling_tmp is not None:
                try:
                    sibling_tmp.unlink(missing_ok=True)
                except Exception:
                    pass

        self.progress_cb(100, "Sharing-Paket erstellt!")
        log.info("Share package created: %s (%.1f MB)",
                 out_path, result.package_size_bytes / 1048576)
        return result

    def _serialize_project(self) -> Dict[str, Any]:
        """Get a deep copy of the project as dict."""
        import copy
        return copy.deepcopy(self.project.to_dict())

    def _collect_media(self, staging: Path, proj_dict: Dict[str, Any],
                       result: ShareExportResult) -> None:
        """Collect and copy all referenced audio files into staging/media/."""
        media_dir = staging / "media"
        seen_names: Set[str] = set()
        max_bytes = int(self.config.max_media_size_mb * 1048576)

        # Collect paths from media items + clip source_path
        paths_to_collect: List[str] = []
        for m in proj_dict.get("media", []):
            if isinstance(m, dict) and m.get("path"):
                paths_to_collect.append(m["path"])
        for c in proj_dict.get("clips", []):
            if isinstance(c, dict) and c.get("source_path"):
                paths_to_collect.append(c["source_path"])

        total = max(1, len(paths_to_collect))
        for i, raw_path in enumerate(paths_to_collect):
            pct = 15 + int(40 * (i / total))
            src = self._resolve_path(raw_path)
            if src is None or not src.exists():
                result.warnings.append(f"Audio nicht gefunden: {raw_path}")
                result.media_files_skipped += 1
                continue

            if src.stat().st_size > max_bytes:
                result.warnings.append(
                    f"Audio zu groß ({src.stat().st_size // 1048576} MB): {src.name}")
                result.media_files_skipped += 1
                continue

            # Unique name
            name = src.name
            if name.lower() in seen_names:
                stem, suffix = src.stem, src.suffix
                counter = 1
                while name.lower() in seen_names:
                    name = f"{stem}_{counter}{suffix}"
                    counter += 1
            seen_names.add(name.lower())

            dest = media_dir / name
            self.progress_cb(pct, f"Media: {name}")
            shutil.copy2(src, dest)
            result.media_files_included += 1

            # Update paths in project dict to relative media/ paths
            rel_path = f"media/{name}"
            self._remap_path_in_project(proj_dict, str(raw_path), rel_path)

    def _resolve_path(self, raw_path: str) -> Optional[Path]:
        """Resolve a path (absolute or relative to project root)."""
        if not raw_path:
            return None
        p = Path(raw_path)
        if p.is_absolute() and p.exists():
            return p
        if self.project_root:
            candidate = self.project_root / p
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _remap_path_in_project(proj_dict: Dict[str, Any],
                                old_path: str, new_path: str) -> None:
        """Replace old_path with new_path in media items and clips."""
        for m in proj_dict.get("media", []):
            if isinstance(m, dict) and m.get("path") == old_path:
                m["path"] = new_path
        for c in proj_dict.get("clips", []):
            if isinstance(c, dict) and c.get("source_path") == old_path:
                c["source_path"] = new_path

    def _strip_personal_data(self, proj_dict: Dict[str, Any]) -> None:
        """Remove personal/sensitive data from project dict."""
        # Strip absolute file paths
        for m in proj_dict.get("media", []):
            if isinstance(m, dict):
                path = m.get("path", "")
                if path and Path(path).is_absolute():
                    m["path"] = f"media/{Path(path).name}"
        for c in proj_dict.get("clips", []):
            if isinstance(c, dict):
                path = c.get("source_path", "")
                if path and Path(path).is_absolute():
                    c["source_path"] = f"media/{Path(path).name}"
        # Remove SF2 absolute paths
        for t in proj_dict.get("tracks", []):
            if isinstance(t, dict):
                sf2 = t.get("sf2_path", "")
                if sf2 and Path(sf2).is_absolute():
                    t["sf2_path"] = Path(sf2).name

    def _build_metadata(self, proj_dict: Dict[str, Any],
                        result: ShareExportResult, content_hash: str) -> ShareMetadata:
        """Build sharing metadata from project data."""
        tracks = proj_dict.get("tracks", [])
        clips = proj_dict.get("clips", [])

        max_beat = 0.0
        for c in clips:
            if isinstance(c, dict):
                end = float(c.get("start_beats", 0)) + float(c.get("length_beats", 0))
                max_beat = max(max_beat, end)

        return ShareMetadata(
            project_name=proj_dict.get("name", "Untitled"),
            author=self.config.author,
            description=self.config.description,
            created_utc=datetime.utcnow().isoformat(timespec="seconds"),
            app_version=__version__,
            bpm=float(proj_dict.get("bpm", 120.0)),
            time_signature=proj_dict.get("time_signature", "4/4"),
            tracks_count=len(tracks),
            clips_count=len(clips),
            media_files_count=result.media_files_included,
            total_duration_beats=max_beat,
            content_hash=content_hash,
            tags=list(self.config.tags),
        )

    @staticmethod
    def _build_readme(metadata: ShareMetadata, result: ShareExportResult) -> str:
        """Generate a human-readable README."""
        bpm = metadata.bpm
        beats = metadata.total_duration_beats
        duration_sec = (beats / bpm * 60) if bpm > 0 else 0
        mins, secs = divmod(int(duration_sec), 60)

        lines = [
            f"# {metadata.project_name}",
            f"",
            f"Created with ChronoScaleStudio (Py_DAW) v{metadata.app_version}",
            f"",
            f"## Project Info",
            f"  BPM:            {bpm}",
            f"  Time Signature: {metadata.time_signature}",
            f"  Duration:       ~{mins}:{secs:02d}",
            f"  Tracks:         {metadata.tracks_count}",
            f"  Clips:          {metadata.clips_count}",
            f"  Audio Files:    {metadata.media_files_count}",
            f"",
        ]
        if metadata.author:
            lines.append(f"  Author:         {metadata.author}")
        if metadata.description:
            lines.append(f"")
            lines.append(f"## Description")
            lines.append(f"  {metadata.description}")
        if metadata.tags:
            lines.append(f"")
            lines.append(f"  Tags: {', '.join(metadata.tags)}")

        lines.extend([
            f"",
            f"## How to Open",
            f"  1. Open ChronoScaleStudio (Py_DAW)",
            f"  2. File → Import → Import Shared Project (.pydaw-share)",
            f"  3. Select this file",
            f"",
            f"## Package Contents",
            f"  project.json   — Full project state",
            f"  metadata.json  — Project metadata",
            f"  media/         — {metadata.media_files_count} audio file(s)",
            f"  README.txt     — This file",
            f"",
            f"Generated: {metadata.created_utc}",
            f"Hash: {metadata.content_hash}",
        ])

        if result.warnings:
            lines.append(f"")
            lines.append(f"## Warnings")
            for w in result.warnings[:20]:
                lines.append(f"  - {w}")

        return "\n".join(lines)

    @staticmethod
    def _validate_package(archive_path: Path) -> None:
        """Basic validation of the generated package."""
        if not zipfile.is_zipfile(archive_path):
            raise ValueError(f"Keine gültige ZIP-Datei: {archive_path}")
        with zipfile.ZipFile(archive_path, "r") as zf:
            names = set(zf.namelist())
            required = {"project.json", "metadata.json", "README.txt"}
            missing = required - names
            if missing:
                raise ValueError(f"Pflichtdateien fehlen: {', '.join(sorted(missing))}")


# ---------------------------------------------------------------------------
# Import: Open shared package
# ---------------------------------------------------------------------------

class ProjectShareImporter:
    """Import a shared project package into Py_DAW."""

    def __init__(
        self,
        package_path: Path,
        project,
        media_dir: Path,
        progress_cb: Optional[ProgressCallback] = None,
    ):
        self.package_path = Path(package_path)
        self.project = project
        self.media_dir = Path(media_dir)
        self.progress_cb: ProgressCallback = progress_cb or (lambda pct, msg: None)

    def preview(self) -> ShareMetadata:
        """Read metadata without importing — for preview in UI."""
        with zipfile.ZipFile(self.package_path, "r") as zf:
            if "metadata.json" in zf.namelist():
                raw = json.loads(zf.read("metadata.json").decode("utf-8"))
                return ShareMetadata.from_dict(raw)
        return ShareMetadata(project_name=self.package_path.stem)

    def import_package(self, replace: bool = False) -> ShareImportResult:
        """Import the shared package into the current project.

        Args:
            replace: If True, replace current project. If False, merge (add tracks).

        Returns:
            ShareImportResult with statistics.
        """
        result = ShareImportResult()

        if not self.package_path.exists():
            raise FileNotFoundError(f"Package nicht gefunden: {self.package_path}")

        self.progress_cb(5, "Paket öffnen …")

        with zipfile.ZipFile(self.package_path, "r") as zf:
            names = zf.namelist()

            # 1. Read metadata
            if "metadata.json" in names:
                meta = ShareMetadata.from_dict(
                    json.loads(zf.read("metadata.json").decode("utf-8")))
                result.project_name = meta.project_name
                result.source_author = meta.author

            # 2. Extract media files
            self.progress_cb(15, "Audio-Dateien extrahieren …")
            audio_map = self._extract_media(zf, names, result)

            # 3. Read project.json
            self.progress_cb(50, "Projekt-Daten laden …")
            if "project.json" not in names:
                raise ValueError("project.json fehlt im Paket")
            proj_dict = json.loads(zf.read("project.json").decode("utf-8"))

        # 4. Apply to project
        self.progress_cb(60, "Projekt importieren …")
        if replace:
            self._replace_project(proj_dict, audio_map, result)
        else:
            self._merge_into_project(proj_dict, audio_map, result)

        self.progress_cb(100, "Import abgeschlossen!")
        return result

    def _extract_media(self, zf: zipfile.ZipFile, names: List[str],
                       result: ShareImportResult) -> Dict[str, Path]:
        """Extract media/ files into project media dir."""
        audio_map: Dict[str, Path] = {}
        self.media_dir.mkdir(parents=True, exist_ok=True)

        media_files = [n for n in names if n.startswith("media/") and not n.endswith("/")]
        total = max(1, len(media_files))

        for i, arc_path in enumerate(media_files):
            pct = 15 + int(30 * (i / total))
            fname = Path(arc_path).name
            self.progress_cb(pct, f"Media: {fname}")

            dest = self.media_dir / fname
            if dest.exists():
                stem, suffix = dest.stem, dest.suffix
                counter = 1
                while dest.exists():
                    dest = self.media_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

            try:
                with zf.open(arc_path) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                audio_map[arc_path] = dest
                result.media_files_extracted += 1
            except Exception as e:
                result.warnings.append(f"Media-Extraktion fehlgeschlagen: {arc_path}: {e}")

        return audio_map

    def _replace_project(self, proj_dict: Dict[str, Any],
                         audio_map: Dict[str, Path],
                         result: ShareImportResult) -> None:
        """Replace current project with shared data."""
        from pydaw.model.project import Project

        # Remap media paths
        self._remap_media_paths(proj_dict, audio_map)

        # Load as new project
        try:
            new_proj = Project.from_dict(proj_dict)
            # Copy all attributes
            for attr in ("name", "bpm", "time_signature", "sample_rate",
                         "tracks", "clips", "media", "midi_notes",
                         "clip_launcher", "automation_manager_lanes",
                         "ghost_layers", "notation_marks"):
                if hasattr(new_proj, attr):
                    setattr(self.project, attr, getattr(new_proj, attr))

            result.tracks_imported = len(new_proj.tracks)
            result.clips_imported = len(new_proj.clips)
        except Exception as e:
            result.warnings.append(f"Projekt-Ersetzung fehlgeschlagen: {e}")

    def _merge_into_project(self, proj_dict: Dict[str, Any],
                            audio_map: Dict[str, Path],
                            result: ShareImportResult) -> None:
        """Merge shared project tracks/clips into current project."""
        from pydaw.model.project import Project, Track, Clip, MediaItem
        from pydaw.model.midi import MidiNote
        from dataclasses import fields as dc_fields

        # Remap media paths
        self._remap_media_paths(proj_dict, audio_map)

        try:
            shared = Project.from_dict(proj_dict)
        except Exception as e:
            result.warnings.append(f"Shared project parse error: {e}")
            return

        # Add tracks (except master)
        for trk in shared.tracks:
            if trk.kind == "master":
                continue
            # Prefix name to avoid confusion
            trk.name = f"[Shared] {trk.name}"
            tracks = [t for t in self.project.tracks if t.kind != "master"]
            master = next((t for t in self.project.tracks if t.kind == "master"), None)
            tracks.append(trk)
            if master:
                tracks.append(master)
            self.project.tracks = tracks
            result.tracks_imported += 1

        # Add clips
        for clip in shared.clips:
            self.project.clips.append(clip)
            result.clips_imported += 1

        # Add MIDI notes
        for clip_id, notes in shared.midi_notes.items():
            self.project.midi_notes[clip_id] = notes

        # Add media
        for mi in shared.media:
            self.project.media.append(mi)

    @staticmethod
    def _remap_media_paths(proj_dict: Dict[str, Any],
                           audio_map: Dict[str, Path]) -> None:
        """Replace relative media/ paths with actual extracted paths."""
        for m in proj_dict.get("media", []):
            if isinstance(m, dict):
                old = m.get("path", "")
                if old in audio_map:
                    m["path"] = str(audio_map[old])
        for c in proj_dict.get("clips", []):
            if isinstance(c, dict):
                old = c.get("source_path", "")
                if old in audio_map:
                    c["source_path"] = str(audio_map[old])


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def export_shared_project(
    project,
    target_path: Path,
    project_root: Optional[Path] = None,
    *,
    author: str = "",
    description: str = "",
    include_media: bool = True,
    progress_cb: Optional[ProgressCallback] = None,
) -> ShareExportResult:
    """High-level entry point for creating a shareable package."""
    config = ShareExportConfig(
        include_media=include_media,
        author=author,
        description=description,
    )
    exporter = ProjectShareExporter(project, project_root, config, progress_cb)
    return exporter.export(target_path)


def import_shared_project(
    package_path: Path,
    project,
    media_dir: Path,
    *,
    replace: bool = False,
    progress_cb: Optional[ProgressCallback] = None,
) -> ShareImportResult:
    """High-level entry point for importing a shared package."""
    importer = ProjectShareImporter(package_path, project, media_dir, progress_cb)
    return importer.import_package(replace=replace)


def preview_shared_project(package_path: Path) -> ShareMetadata:
    """Preview a shared package without importing."""
    importer = ProjectShareImporter(package_path, None, Path("."))
    return importer.preview()
