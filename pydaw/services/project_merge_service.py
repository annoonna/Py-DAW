"""Project Merge Service — Foundation for Collaborative Editing.

Implements a 3-way merge strategy for Py_DAW projects:
  - Base (common ancestor) + Ours (local changes) + Theirs (remote changes)
  - Automatic merge for non-conflicting changes
  - Conflict detection for overlapping modifications
  - Conflict resolution strategies (ours-wins, theirs-wins, manual)

This is the data-layer foundation. A full collaborative system would add:
  - Network transport (WebSocket/P2P)
  - Operational Transform or CRDT for real-time sync
  - User presence / cursor sharing

For now, this enables:
  - Offline collaboration: Two users work on copies, then merge
  - Branch-like workflow: Snapshot → experiment → merge back
  - Import with merge: Import shared project alongside existing work

v0.0.20.658 — AP10 Phase 10D (Claude Opus 4.6, 2026-03-20)
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MergeConflict:
    """A single merge conflict between two project versions."""
    category: str = ""        # "track" | "clip" | "transport" | "automation"
    item_id: str = ""         # ID of the conflicting item
    item_name: str = ""       # human-readable name
    field_name: str = ""      # which field conflicts
    base_value: str = ""      # value in common ancestor
    ours_value: str = ""      # value in local version
    theirs_value: str = ""    # value in remote version
    resolution: str = ""      # "ours" | "theirs" | "manual" | "" (unresolved)
    resolved_value: str = ""  # the value that was chosen


@dataclass
class MergeResult:
    """Result of a 3-way merge operation."""
    merged_project: Optional[Dict[str, Any]] = None
    auto_merged: int = 0           # changes merged automatically
    conflicts: List[MergeConflict] = field(default_factory=list)
    conflicts_resolved: int = 0
    conflicts_unresolved: int = 0
    tracks_added: int = 0
    tracks_removed: int = 0
    clips_added: int = 0
    clips_removed: int = 0
    success: bool = False

    def summary(self) -> str:
        lines = [
            "Merge Result:",
            f"  Auto-merged: {self.auto_merged} changes",
            f"  Tracks: +{self.tracks_added} -{self.tracks_removed}",
            f"  Clips: +{self.clips_added} -{self.clips_removed}",
            f"  Conflicts: {len(self.conflicts)} "
            f"({self.conflicts_resolved} resolved, {self.conflicts_unresolved} unresolved)",
            f"  Success: {self.success}",
        ]
        if self.conflicts:
            lines.append("  Conflict details:")
            for c in self.conflicts[:20]:
                res = f" → {c.resolution}" if c.resolution else " (UNRESOLVED)"
                lines.append(f"    [{c.category}] {c.item_name}.{c.field_name}{res}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3-Way Merge Engine
# ---------------------------------------------------------------------------

class ProjectMergeEngine:
    """3-way merge for Py_DAW project dicts.

    Usage:
        engine = ProjectMergeEngine(base_dict, ours_dict, theirs_dict)
        result = engine.merge(strategy="ours-wins")
        if result.success:
            project = Project.from_dict(result.merged_project)
    """

    def __init__(
        self,
        base: Dict[str, Any],
        ours: Dict[str, Any],
        theirs: Dict[str, Any],
    ):
        self.base = copy.deepcopy(base)
        self.ours = copy.deepcopy(ours)
        self.theirs = copy.deepcopy(theirs)
        self.conflicts: List[MergeConflict] = []
        self.auto_merged = 0

    def merge(self, strategy: str = "ours-wins") -> MergeResult:
        """Perform the 3-way merge.

        Args:
            strategy: Conflict resolution strategy
                - "ours-wins": Local changes take priority
                - "theirs-wins": Remote changes take priority
                - "manual": Leave conflicts unresolved (for UI resolution)

        Returns:
            MergeResult with the merged project dict (if successful)
        """
        result = MergeResult()

        # Start with a copy of ours as the base for merging
        merged = copy.deepcopy(self.ours)

        # 1. Merge transport settings
        self._merge_transport(merged, strategy)

        # 2. Merge tracks
        self._merge_tracks(merged, result, strategy)

        # 3. Merge clips
        self._merge_clips(merged, result, strategy)

        # 4. Merge MIDI notes
        self._merge_midi_notes(merged, result)

        # 5. Merge automation
        self._merge_automation(merged, result, strategy)

        # 6. Merge media
        self._merge_media(merged, result)

        # Finalize
        result.merged_project = merged
        result.conflicts = self.conflicts
        result.auto_merged = self.auto_merged
        result.conflicts_resolved = sum(1 for c in self.conflicts if c.resolution)
        result.conflicts_unresolved = sum(1 for c in self.conflicts if not c.resolution)
        result.success = result.conflicts_unresolved == 0
        return result

    # ------------------------------------------------------------------
    # Transport merge
    # ------------------------------------------------------------------

    def _merge_transport(self, merged: Dict, strategy: str) -> None:
        """Merge BPM, time signature, sample rate."""
        for key in ("bpm", "time_signature", "sample_rate"):
            base_val = self.base.get(key)
            ours_val = self.ours.get(key)
            theirs_val = self.theirs.get(key)

            # Both unchanged → keep base
            if ours_val == base_val and theirs_val == base_val:
                continue

            # Only one side changed → take the change
            if ours_val == base_val and theirs_val != base_val:
                merged[key] = theirs_val
                self.auto_merged += 1
            elif ours_val != base_val and theirs_val == base_val:
                # Already in merged (copy of ours)
                self.auto_merged += 1
            elif ours_val == theirs_val:
                # Both changed to same value
                self.auto_merged += 1
            else:
                # Conflict: both changed to different values
                conflict = MergeConflict(
                    category="transport",
                    field_name=key,
                    base_value=str(base_val),
                    ours_value=str(ours_val),
                    theirs_value=str(theirs_val),
                )
                self._resolve_conflict(conflict, merged, key, strategy)
                self.conflicts.append(conflict)

    # ------------------------------------------------------------------
    # Track merge
    # ------------------------------------------------------------------

    def _merge_tracks(self, merged: Dict, result: MergeResult, strategy: str) -> None:
        """Merge track lists using ID-based matching."""
        base_tracks = {t.get("id", ""): t for t in self.base.get("tracks", [])
                       if isinstance(t, dict)}
        ours_tracks = {t.get("id", ""): t for t in self.ours.get("tracks", [])
                       if isinstance(t, dict)}
        theirs_tracks = {t.get("id", ""): t for t in self.theirs.get("tracks", [])
                         if isinstance(t, dict)}

        base_ids = set(base_tracks.keys())
        ours_ids = set(ours_tracks.keys())
        theirs_ids = set(theirs_tracks.keys())

        # Tracks added by theirs (not in base, not in ours)
        theirs_added = theirs_ids - base_ids
        for tid in theirs_added:
            if tid not in ours_ids:
                # Add new track from theirs
                merged_tracks = merged.get("tracks", [])
                # Insert before master
                master_idx = next((i for i, t in enumerate(merged_tracks)
                                   if isinstance(t, dict) and t.get("kind") == "master"),
                                  len(merged_tracks))
                merged_tracks.insert(master_idx, copy.deepcopy(theirs_tracks[tid]))
                merged["tracks"] = merged_tracks
                result.tracks_added += 1
                self.auto_merged += 1

        # Tracks removed by theirs (in base, not in theirs)
        theirs_removed = base_ids - theirs_ids
        for tid in theirs_removed:
            if tid in ours_ids:
                # Theirs removed it, but ours still has it
                # Check if ours modified it
                ours_t = ours_tracks.get(tid, {})
                base_t = base_tracks.get(tid, {})
                if self._track_changed(base_t, ours_t):
                    # Conflict: theirs removed, ours modified
                    conflict = MergeConflict(
                        category="track",
                        item_id=tid,
                        item_name=ours_t.get("name", "?"),
                        field_name="existence",
                        base_value="exists",
                        ours_value="modified",
                        theirs_value="removed",
                    )
                    if strategy == "theirs-wins":
                        conflict.resolution = "theirs"
                        merged["tracks"] = [t for t in merged.get("tracks", [])
                                            if not (isinstance(t, dict) and t.get("id") == tid)]
                        result.tracks_removed += 1
                    else:
                        conflict.resolution = "ours"
                    self.conflicts.append(conflict)
                else:
                    # Both agree: remove it
                    merged["tracks"] = [t for t in merged.get("tracks", [])
                                        if not (isinstance(t, dict) and t.get("id") == tid)]
                    result.tracks_removed += 1
                    self.auto_merged += 1

        # Tracks modified by both
        common_ids = base_ids & ours_ids & theirs_ids
        for tid in common_ids:
            self._merge_single_track(
                base_tracks[tid], ours_tracks[tid], theirs_tracks[tid],
                merged, strategy,
            )

    def _merge_single_track(self, base_t: Dict, ours_t: Dict, theirs_t: Dict,
                            merged: Dict, strategy: str) -> None:
        """Merge individual track fields."""
        tid = base_t.get("id", "")
        merge_fields = ["name", "volume", "pan", "muted", "solo",
                        "instrument_enabled", "plugin_type", "channel_config"]

        merged_track = None
        for t in merged.get("tracks", []):
            if isinstance(t, dict) and t.get("id") == tid:
                merged_track = t
                break
        if merged_track is None:
            return

        for fld in merge_fields:
            base_val = base_t.get(fld)
            ours_val = ours_t.get(fld)
            theirs_val = theirs_t.get(fld)

            if ours_val == base_val and theirs_val == base_val:
                continue
            if ours_val == base_val and theirs_val != base_val:
                merged_track[fld] = theirs_val
                self.auto_merged += 1
            elif ours_val != base_val and theirs_val == base_val:
                self.auto_merged += 1
            elif ours_val == theirs_val:
                self.auto_merged += 1
            else:
                conflict = MergeConflict(
                    category="track",
                    item_id=tid,
                    item_name=ours_t.get("name", "?"),
                    field_name=fld,
                    base_value=str(base_val),
                    ours_value=str(ours_val),
                    theirs_value=str(theirs_val),
                )
                self._resolve_conflict_on_dict(conflict, merged_track, fld, strategy)
                self.conflicts.append(conflict)

    @staticmethod
    def _track_changed(base_t: Dict, other_t: Dict) -> bool:
        """Check if a track was modified compared to base."""
        for key in ("name", "volume", "pan", "muted", "solo", "plugin_type"):
            if base_t.get(key) != other_t.get(key):
                return True
        return False

    # ------------------------------------------------------------------
    # Clip merge
    # ------------------------------------------------------------------

    def _merge_clips(self, merged: Dict, result: MergeResult, strategy: str) -> None:
        """Merge clip lists using ID-based matching."""
        base_clips = {c.get("id", ""): c for c in self.base.get("clips", [])
                      if isinstance(c, dict)}
        theirs_clips = {c.get("id", ""): c for c in self.theirs.get("clips", [])
                        if isinstance(c, dict)}

        base_ids = set(base_clips.keys())
        theirs_ids = set(theirs_clips.keys())

        # Clips added by theirs
        for cid in sorted(theirs_ids - base_ids):
            merged.setdefault("clips", []).append(copy.deepcopy(theirs_clips[cid]))
            result.clips_added += 1
            self.auto_merged += 1

        # Clips removed by theirs
        theirs_removed = base_ids - theirs_ids
        ours_clips = {c.get("id", ""): c for c in self.ours.get("clips", [])
                      if isinstance(c, dict)}
        for cid in theirs_removed:
            if cid in ours_clips:
                # Auto-remove if ours didn't modify it
                merged["clips"] = [c for c in merged.get("clips", [])
                                   if not (isinstance(c, dict) and c.get("id") == cid)]
                result.clips_removed += 1
                self.auto_merged += 1

    # ------------------------------------------------------------------
    # MIDI notes merge
    # ------------------------------------------------------------------

    def _merge_midi_notes(self, merged: Dict, result: MergeResult) -> None:
        """Merge MIDI notes — add new clip notes from theirs."""
        base_notes = self.base.get("midi_notes", {}) or {}
        theirs_notes = self.theirs.get("midi_notes", {}) or {}

        merged_notes = merged.get("midi_notes", {}) or {}
        if not isinstance(merged_notes, dict):
            merged_notes = {}

        for clip_id, notes in theirs_notes.items():
            if clip_id not in base_notes and clip_id not in merged_notes:
                merged_notes[clip_id] = copy.deepcopy(notes)
                self.auto_merged += 1

        merged["midi_notes"] = merged_notes

    # ------------------------------------------------------------------
    # Automation merge
    # ------------------------------------------------------------------

    def _merge_automation(self, merged: Dict, result: MergeResult, strategy: str) -> None:
        """Merge automation lanes — add new lanes from theirs."""
        base_lanes = self.base.get("automation_manager_lanes", {}) or {}
        theirs_lanes = self.theirs.get("automation_manager_lanes", {}) or {}

        merged_lanes = merged.get("automation_manager_lanes", {}) or {}
        if not isinstance(merged_lanes, dict):
            merged_lanes = {}

        for key, lane in theirs_lanes.items():
            if key not in base_lanes and key not in merged_lanes:
                merged_lanes[key] = copy.deepcopy(lane)
                self.auto_merged += 1

        merged["automation_manager_lanes"] = merged_lanes

    # ------------------------------------------------------------------
    # Media merge
    # ------------------------------------------------------------------

    def _merge_media(self, merged: Dict, result: MergeResult) -> None:
        """Merge media items — add new from theirs."""
        base_media_ids = {m.get("id", ""): m for m in self.base.get("media", [])
                         if isinstance(m, dict)}
        merged_media_ids = {m.get("id", ""): m for m in merged.get("media", [])
                           if isinstance(m, dict)}

        for m in self.theirs.get("media", []):
            if isinstance(m, dict):
                mid = m.get("id", "")
                if mid and mid not in base_media_ids and mid not in merged_media_ids:
                    merged.setdefault("media", []).append(copy.deepcopy(m))
                    self.auto_merged += 1

    # ------------------------------------------------------------------
    # Conflict resolution
    # ------------------------------------------------------------------

    def _resolve_conflict(self, conflict: MergeConflict, merged: Dict,
                          key: str, strategy: str) -> None:
        """Resolve a top-level dict conflict."""
        if strategy == "ours-wins":
            conflict.resolution = "ours"
            conflict.resolved_value = conflict.ours_value
        elif strategy == "theirs-wins":
            conflict.resolution = "theirs"
            conflict.resolved_value = conflict.theirs_value
            # Apply theirs value
            try:
                merged[key] = type(self.base.get(key))(conflict.theirs_value)
            except (ValueError, TypeError):
                merged[key] = conflict.theirs_value
        # "manual" → leave unresolved

    def _resolve_conflict_on_dict(self, conflict: MergeConflict, target: Dict,
                                  key: str, strategy: str) -> None:
        """Resolve a conflict on a nested dict (e.g. track field)."""
        if strategy == "ours-wins":
            conflict.resolution = "ours"
            conflict.resolved_value = conflict.ours_value
        elif strategy == "theirs-wins":
            conflict.resolution = "theirs"
            conflict.resolved_value = conflict.theirs_value
            try:
                base_type = type(self.base.get("tracks", [{}])[0].get(key, ""))
                target[key] = base_type(conflict.theirs_value)
            except (ValueError, TypeError, IndexError):
                target[key] = conflict.theirs_value


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def merge_projects(
    base: Dict[str, Any],
    ours: Dict[str, Any],
    theirs: Dict[str, Any],
    strategy: str = "ours-wins",
) -> MergeResult:
    """High-level 3-way merge of project dicts.

    Args:
        base: Common ancestor project dict
        ours: Local version project dict
        theirs: Remote version project dict
        strategy: "ours-wins" | "theirs-wins" | "manual"

    Returns:
        MergeResult with merged project and conflict info
    """
    engine = ProjectMergeEngine(base, ours, theirs)
    return engine.merge(strategy=strategy)


def merge_from_snapshots(
    version_service,
    base_id: str,
    ours_id: str,
    theirs_id: str,
    strategy: str = "ours-wins",
) -> MergeResult:
    """Merge using snapshot IDs from ProjectVersionService."""
    base = version_service.load_snapshot_data(base_id)
    ours = version_service.load_snapshot_data(ours_id)
    theirs = version_service.load_snapshot_data(theirs_id)

    if base is None or ours is None or theirs is None:
        result = MergeResult()
        result.conflicts.append(MergeConflict(
            category="error", field_name="snapshot_load",
            base_value=base_id, ours_value=ours_id, theirs_value=theirs_id,
        ))
        return result

    return merge_projects(base, ours, theirs, strategy)
