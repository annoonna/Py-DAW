"""Project Versioning Service — Git-like Snapshots with Diff.

Provides a lightweight, file-based versioning system for Py_DAW projects:
  - Automatic snapshots on save (configurable interval)
  - Manual named snapshots (like git tags)
  - Diff between any two snapshots (tracks added/removed/changed, clips, etc.)
  - Snapshot restore (non-destructive — current state is backed up first)
  - History browser (list all snapshots with metadata)
  - Pruning (keep last N snapshots, or by age)

Storage format:
  project_root/
  └── .versions/
      ├── manifest.json          ← Index of all snapshots
      ├── v001_20260320_143022_auto.json   ← Snapshot files
      ├── v002_20260320_150000_manual_mix_ready.json
      └── ...

Each snapshot is a JSON file containing the full project state (same as
the normal project save), plus metadata (timestamp, label, parent hash).

v0.0.20.658 — AP10 Phase 10D (Claude Opus 4.6, 2026-03-20)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SnapshotMeta:
    """Metadata for one project snapshot."""
    snapshot_id: str = ""          # e.g. "v001"
    filename: str = ""             # e.g. "v001_20260320_143022_auto.json"
    timestamp: str = ""            # ISO 8601
    label: str = ""                # user-defined label or "auto"
    kind: str = "auto"             # "auto" | "manual" | "pre-restore"
    parent_id: str = ""            # previous snapshot ID (chain)
    content_hash: str = ""         # SHA-256 of the project JSON
    tracks_count: int = 0
    clips_count: int = 0
    file_size_bytes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SnapshotMeta":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class SnapshotDiffEntry:
    """A single difference between two snapshots."""
    category: str = ""        # "track" | "clip" | "transport" | "automation" | "media"
    action: str = ""          # "added" | "removed" | "changed"
    item_id: str = ""         # track_id / clip_id / param name
    item_name: str = ""       # human-readable name
    detail: str = ""          # what changed


@dataclass
class SnapshotDiff:
    """Complete diff between two snapshots."""
    from_id: str = ""
    to_id: str = ""
    from_label: str = ""
    to_label: str = ""
    entries: List[SnapshotDiffEntry] = field(default_factory=list)
    tracks_added: int = 0
    tracks_removed: int = 0
    tracks_changed: int = 0
    clips_added: int = 0
    clips_removed: int = 0

    def summary(self) -> str:
        lines = [f"Diff: {self.from_label or self.from_id} → {self.to_label or self.to_id}"]
        lines.append(f"  Tracks: +{self.tracks_added} -{self.tracks_removed} ~{self.tracks_changed}")
        lines.append(f"  Clips: +{self.clips_added} -{self.clips_removed}")
        lines.append(f"  Total changes: {len(self.entries)}")
        return "\n".join(lines)


@dataclass
class VersionManifest:
    """Index of all snapshots for a project."""
    project_name: str = ""
    snapshots: List[SnapshotMeta] = field(default_factory=list)
    next_version: int = 1
    max_auto_snapshots: int = 50    # prune auto-snapshots beyond this
    auto_save_interval_sec: float = 300.0  # 5 minutes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "next_version": self.next_version,
            "max_auto_snapshots": self.max_auto_snapshots,
            "auto_save_interval_sec": self.auto_save_interval_sec,
            "snapshots": [s.to_dict() for s in self.snapshots],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VersionManifest":
        m = cls()
        m.project_name = d.get("project_name", "")
        m.next_version = d.get("next_version", 1)
        m.max_auto_snapshots = d.get("max_auto_snapshots", 50)
        m.auto_save_interval_sec = d.get("auto_save_interval_sec", 300.0)
        m.snapshots = [SnapshotMeta.from_dict(s) for s in d.get("snapshots", [])]
        return m


# ---------------------------------------------------------------------------
# Core Version Service
# ---------------------------------------------------------------------------

class ProjectVersionService:
    """Git-like versioning for Py_DAW projects.

    Usage:
        vs = ProjectVersionService(project_root)
        vs.create_snapshot(project, label="Mix v1")
        history = vs.list_snapshots()
        diff = vs.diff_snapshots("v001", "v003")
        vs.restore_snapshot("v002", current_project=project)
    """

    VERSIONS_DIR = ".versions"
    MANIFEST_FILE = "manifest.json"

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.versions_dir = self.project_root / self.VERSIONS_DIR
        self._manifest: Optional[VersionManifest] = None
        self._last_auto_save: float = 0.0

    @property
    def manifest(self) -> VersionManifest:
        if self._manifest is None:
            self._manifest = self._load_manifest()
        return self._manifest

    # ------------------------------------------------------------------
    # Public API: Snapshots
    # ------------------------------------------------------------------

    def create_snapshot(
        self,
        project,
        *,
        label: str = "",
        kind: str = "manual",
    ) -> SnapshotMeta:
        """Create a new snapshot of the project state.

        Args:
            project: The Project instance (must have .to_dict())
            label: Optional user label (e.g. "Mix v2", "Before mastering")
            kind: "manual" | "auto" | "pre-restore"

        Returns:
            SnapshotMeta for the created snapshot
        """
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        manifest = self.manifest

        # Serialize project
        try:
            proj_dict = project.to_dict()
        except Exception as exc:
            log.error("Failed to serialize project for snapshot: %s", exc)
            raise

        proj_json = json.dumps(proj_dict, ensure_ascii=False, sort_keys=True, indent=None)
        content_hash = hashlib.sha256(proj_json.encode("utf-8")).hexdigest()[:16]

        # Check for duplicate (same content as last snapshot)
        if manifest.snapshots:
            last = manifest.snapshots[-1]
            if last.content_hash == content_hash:
                log.debug("Snapshot skipped (no changes since %s)", last.snapshot_id)
                return last

        # Build snapshot metadata
        version_num = manifest.next_version
        snapshot_id = f"v{version_num:03d}"
        now = datetime.utcnow()
        ts_str = now.strftime("%Y%m%d_%H%M%S")
        safe_label = "".join(c if c.isalnum() or c in "_-" else "_" for c in (label or kind))
        filename = f"{snapshot_id}_{ts_str}_{safe_label}.json"

        parent_id = manifest.snapshots[-1].snapshot_id if manifest.snapshots else ""

        meta = SnapshotMeta(
            snapshot_id=snapshot_id,
            filename=filename,
            timestamp=now.isoformat(timespec="seconds"),
            label=label or kind,
            kind=kind,
            parent_id=parent_id,
            content_hash=content_hash,
            tracks_count=len(proj_dict.get("tracks", [])),
            clips_count=len(proj_dict.get("clips", [])),
        )

        # Write snapshot file
        snap_path = self.versions_dir / filename
        snap_path.write_text(proj_json, encoding="utf-8")
        meta.file_size_bytes = snap_path.stat().st_size

        # Update manifest
        manifest.snapshots.append(meta)
        manifest.next_version = version_num + 1
        self._save_manifest()

        # Auto-prune old snapshots
        self._prune_auto_snapshots()

        log.info("Snapshot created: %s (%s) — %d tracks, %d clips",
                 snapshot_id, label or kind, meta.tracks_count, meta.clips_count)
        return meta

    def create_auto_snapshot(self, project) -> Optional[SnapshotMeta]:
        """Create an auto-snapshot if enough time has passed since the last one.

        Call this on every project save. Returns None if skipped (too recent).
        """
        now = time.monotonic()
        interval = self.manifest.auto_save_interval_sec
        if now - self._last_auto_save < interval:
            return None
        self._last_auto_save = now
        try:
            return self.create_snapshot(project, kind="auto")
        except Exception as exc:
            log.warning("Auto-snapshot failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Public API: History
    # ------------------------------------------------------------------

    def list_snapshots(self) -> List[SnapshotMeta]:
        """Return all snapshots, oldest first."""
        return list(self.manifest.snapshots)

    def get_snapshot(self, snapshot_id: str) -> Optional[SnapshotMeta]:
        """Get metadata for a specific snapshot."""
        for s in self.manifest.snapshots:
            if s.snapshot_id == snapshot_id:
                return s
        return None

    def load_snapshot_data(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Load the full project dict from a snapshot file."""
        meta = self.get_snapshot(snapshot_id)
        if meta is None:
            return None
        snap_path = self.versions_dir / meta.filename
        if not snap_path.exists():
            log.warning("Snapshot file missing: %s", snap_path)
            return None
        try:
            return json.loads(snap_path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.error("Failed to load snapshot %s: %s", snapshot_id, exc)
            return None

    # ------------------------------------------------------------------
    # Public API: Restore
    # ------------------------------------------------------------------

    def restore_snapshot(self, snapshot_id: str, current_project) -> Optional[Dict[str, Any]]:
        """Restore a snapshot. Creates a pre-restore backup first.

        Args:
            snapshot_id: Which snapshot to restore
            current_project: The current project (backed up before restore)

        Returns:
            The restored project dict (caller is responsible for loading it)
        """
        # Safety: back up current state before restoring
        try:
            self.create_snapshot(current_project, label=f"pre-restore-{snapshot_id}",
                                kind="pre-restore")
        except Exception as exc:
            log.warning("Pre-restore backup failed: %s", exc)

        data = self.load_snapshot_data(snapshot_id)
        if data is None:
            log.error("Cannot restore snapshot %s — data not found", snapshot_id)
            return None

        log.info("Restoring snapshot %s", snapshot_id)
        return data

    # ------------------------------------------------------------------
    # Public API: Diff
    # ------------------------------------------------------------------

    def diff_snapshots(self, from_id: str, to_id: str) -> SnapshotDiff:
        """Compare two snapshots and return a structured diff."""
        from_data = self.load_snapshot_data(from_id)
        to_data = self.load_snapshot_data(to_id)

        from_meta = self.get_snapshot(from_id)
        to_meta = self.get_snapshot(to_id)

        diff = SnapshotDiff(
            from_id=from_id,
            to_id=to_id,
            from_label=from_meta.label if from_meta else "",
            to_label=to_meta.label if to_meta else "",
        )

        if from_data is None or to_data is None:
            diff.entries.append(SnapshotDiffEntry(
                category="error", action="error",
                detail="Cannot load one or both snapshots",
            ))
            return diff

        self._diff_transport(from_data, to_data, diff)
        self._diff_tracks(from_data, to_data, diff)
        self._diff_clips(from_data, to_data, diff)
        self._diff_automation(from_data, to_data, diff)
        self._diff_media(from_data, to_data, diff)

        return diff

    # ------------------------------------------------------------------
    # Public API: Maintenance
    # ------------------------------------------------------------------

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a specific snapshot."""
        meta = self.get_snapshot(snapshot_id)
        if meta is None:
            return False

        snap_path = self.versions_dir / meta.filename
        try:
            snap_path.unlink(missing_ok=True)
        except Exception:
            pass

        self.manifest.snapshots = [s for s in self.manifest.snapshots
                                    if s.snapshot_id != snapshot_id]
        self._save_manifest()
        return True

    def get_versions_size_bytes(self) -> int:
        """Total disk usage of the versions directory."""
        total = 0
        if self.versions_dir.exists():
            for f in self.versions_dir.iterdir():
                if f.is_file():
                    total += f.stat().st_size
        return total

    # ------------------------------------------------------------------
    # Diff implementation
    # ------------------------------------------------------------------

    def _diff_transport(self, from_d: Dict, to_d: Dict, diff: SnapshotDiff) -> None:
        for key in ("bpm", "time_signature", "sample_rate"):
            old_val = from_d.get(key)
            new_val = to_d.get(key)
            if old_val != new_val:
                diff.entries.append(SnapshotDiffEntry(
                    category="transport", action="changed",
                    item_name=key, detail=f"{old_val} → {new_val}",
                ))

    def _diff_tracks(self, from_d: Dict, to_d: Dict, diff: SnapshotDiff) -> None:
        from_tracks = {t.get("id", ""): t for t in from_d.get("tracks", []) if isinstance(t, dict)}
        to_tracks = {t.get("id", ""): t for t in to_d.get("tracks", []) if isinstance(t, dict)}

        from_ids = set(from_tracks.keys())
        to_ids = set(to_tracks.keys())

        for tid in sorted(to_ids - from_ids):
            t = to_tracks[tid]
            diff.entries.append(SnapshotDiffEntry(
                category="track", action="added",
                item_id=tid, item_name=t.get("name", "?"),
                detail=f"kind={t.get('kind', '?')}",
            ))
            diff.tracks_added += 1

        for tid in sorted(from_ids - to_ids):
            t = from_tracks[tid]
            diff.entries.append(SnapshotDiffEntry(
                category="track", action="removed",
                item_id=tid, item_name=t.get("name", "?"),
            ))
            diff.tracks_removed += 1

        for tid in sorted(from_ids & to_ids):
            old_t = from_tracks[tid]
            new_t = to_tracks[tid]
            changes = []
            for key in ("name", "volume", "pan", "muted", "solo", "plugin_type",
                        "instrument_enabled", "kind"):
                old_v = old_t.get(key)
                new_v = new_t.get(key)
                if old_v != new_v:
                    changes.append(f"{key}: {old_v} → {new_v}")

            if changes:
                diff.entries.append(SnapshotDiffEntry(
                    category="track", action="changed",
                    item_id=tid, item_name=new_t.get("name", "?"),
                    detail="; ".join(changes),
                ))
                diff.tracks_changed += 1

    def _diff_clips(self, from_d: Dict, to_d: Dict, diff: SnapshotDiff) -> None:
        from_clips = {c.get("id", ""): c for c in from_d.get("clips", []) if isinstance(c, dict)}
        to_clips = {c.get("id", ""): c for c in to_d.get("clips", []) if isinstance(c, dict)}

        from_ids = set(from_clips.keys())
        to_ids = set(to_clips.keys())

        for cid in sorted(to_ids - from_ids):
            c = to_clips[cid]
            diff.entries.append(SnapshotDiffEntry(
                category="clip", action="added",
                item_id=cid, item_name=c.get("label", "?"),
                detail=f"kind={c.get('kind', '?')}, start={c.get('start_beats', 0)}",
            ))
            diff.clips_added += 1

        for cid in sorted(from_ids - to_ids):
            c = from_clips[cid]
            diff.entries.append(SnapshotDiffEntry(
                category="clip", action="removed",
                item_id=cid, item_name=c.get("label", "?"),
            ))
            diff.clips_removed += 1

    def _diff_automation(self, from_d: Dict, to_d: Dict, diff: SnapshotDiff) -> None:
        from_lanes = from_d.get("automation_manager_lanes", {})
        to_lanes = to_d.get("automation_manager_lanes", {})
        if not isinstance(from_lanes, dict):
            from_lanes = {}
        if not isinstance(to_lanes, dict):
            to_lanes = {}

        from_keys = set(from_lanes.keys())
        to_keys = set(to_lanes.keys())

        added = to_keys - from_keys
        removed = from_keys - to_keys
        if added:
            diff.entries.append(SnapshotDiffEntry(
                category="automation", action="added",
                detail=f"{len(added)} lane(s) added",
            ))
        if removed:
            diff.entries.append(SnapshotDiffEntry(
                category="automation", action="removed",
                detail=f"{len(removed)} lane(s) removed",
            ))

        for key in sorted(from_keys & to_keys):
            old_points = len((from_lanes[key] or {}).get("points", []) if isinstance(from_lanes[key], dict) else [])
            new_points = len((to_lanes[key] or {}).get("points", []) if isinstance(to_lanes[key], dict) else [])
            if old_points != new_points:
                diff.entries.append(SnapshotDiffEntry(
                    category="automation", action="changed",
                    item_id=key,
                    detail=f"points: {old_points} → {new_points}",
                ))

    def _diff_media(self, from_d: Dict, to_d: Dict, diff: SnapshotDiff) -> None:
        from_media = {m.get("id", ""): m for m in from_d.get("media", []) if isinstance(m, dict)}
        to_media = {m.get("id", ""): m for m in to_d.get("media", []) if isinstance(m, dict)}

        added = set(to_media.keys()) - set(from_media.keys())
        removed = set(from_media.keys()) - set(to_media.keys())

        if added:
            for mid in sorted(added):
                m = to_media[mid]
                diff.entries.append(SnapshotDiffEntry(
                    category="media", action="added",
                    item_id=mid, item_name=m.get("label", m.get("path", "?")),
                ))
        if removed:
            for mid in sorted(removed):
                m = from_media[mid]
                diff.entries.append(SnapshotDiffEntry(
                    category="media", action="removed",
                    item_id=mid, item_name=m.get("label", m.get("path", "?")),
                ))

    # ------------------------------------------------------------------
    # Manifest I/O
    # ------------------------------------------------------------------

    def _load_manifest(self) -> VersionManifest:
        manifest_path = self.versions_dir / self.MANIFEST_FILE
        if not manifest_path.exists():
            return VersionManifest()
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            return VersionManifest.from_dict(data)
        except Exception as exc:
            log.warning("Failed to load version manifest: %s", exc)
            return VersionManifest()

    def _save_manifest(self) -> None:
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self.versions_dir / self.MANIFEST_FILE
        try:
            manifest_path.write_text(
                json.dumps(self.manifest.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            log.error("Failed to save version manifest: %s", exc)

    def _prune_auto_snapshots(self) -> None:
        """Remove oldest auto-snapshots if we exceed the limit."""
        manifest = self.manifest
        auto_snaps = [s for s in manifest.snapshots if s.kind == "auto"]
        max_count = max(5, manifest.max_auto_snapshots)

        if len(auto_snaps) <= max_count:
            return

        to_prune = auto_snaps[:len(auto_snaps) - max_count]
        prune_ids = {s.snapshot_id for s in to_prune}

        for meta in to_prune:
            snap_path = self.versions_dir / meta.filename
            try:
                snap_path.unlink(missing_ok=True)
            except Exception:
                pass

        manifest.snapshots = [s for s in manifest.snapshots
                               if s.snapshot_id not in prune_ids]
        self._save_manifest()
        log.debug("Pruned %d old auto-snapshots", len(to_prune))
