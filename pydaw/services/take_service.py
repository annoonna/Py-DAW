"""TakeService — Take-Lanes and Comping logic for loop-recording.

v0.0.20.639 — AP2 Phase 2D

Responsibilities:
- Group multiple recording passes into take groups
- Manage take ordering (newest on top)
- Comp-Tool: select regions from different takes
- Flatten: merge comp into a single clip
- Take management: rename, delete, reorder

Architecture:
- Takes are regular Clip objects with matching take_group_id
- The "active" take (is_comp_active=True) is what the engine plays
- CompRegion list on Track defines which take plays which section
- TakeService is stateless: reads/writes via ProjectService
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from pydaw.model.project import Clip, CompRegion, Track

log = logging.getLogger(__name__)


class TakeService:
    """Service for managing take-lanes and comping.

    Works with the project model — no audio engine coupling.
    """

    def __init__(self, project_service=None):
        self._project = project_service

    def set_project_service(self, ps) -> None:
        self._project = ps

    # ──────────────────────────────────────────────────────
    # Take Group Management
    # ──────────────────────────────────────────────────────

    def create_take_group(self, track_id: str, start_beat: float,
                          length_beats: float) -> str:
        """Create a new take group ID for loop-recording on a track.

        All takes recorded in the same loop region share this group ID.

        Returns:
            The new take_group_id string.
        """
        from pydaw.model.project import new_id
        group_id = new_id("tkg")
        log.info("Created take group '%s' on track '%s' at beat %.2f (len %.2f)",
                 group_id, track_id, start_beat, length_beats)
        return group_id

    def get_takes_for_group(self, take_group_id: str) -> List['Clip']:
        """Get all clips belonging to a take group, ordered by take_index."""
        if not self._project or not take_group_id:
            return []
        try:
            clips = list(self._project.ctx.project.clips or [])
            takes = [c for c in clips if getattr(c, 'take_group_id', '') == take_group_id]
            takes.sort(key=lambda c: int(getattr(c, 'take_index', 0)))
            return takes
        except Exception:
            return []

    def get_take_groups_for_track(self, track_id: str) -> Dict[str, List['Clip']]:
        """Get all take groups on a track.

        Returns:
            Dict of take_group_id -> list of clips (sorted by take_index).
        """
        if not self._project:
            return {}
        try:
            clips = list(self._project.ctx.project.clips or [])
            groups: Dict[str, List['Clip']] = {}
            for c in clips:
                if getattr(c, 'track_id', '') != track_id:
                    continue
                gid = getattr(c, 'take_group_id', '')
                if not gid:
                    continue
                groups.setdefault(gid, []).append(c)
            for gid in groups:
                groups[gid].sort(key=lambda c: int(getattr(c, 'take_index', 0)))
            return groups
        except Exception:
            return {}

    def get_active_take(self, take_group_id: str) -> Optional['Clip']:
        """Get the currently active take in a group (the one that plays back)."""
        takes = self.get_takes_for_group(take_group_id)
        for t in takes:
            if getattr(t, 'is_comp_active', False):
                return t
        # Fallback: return first take
        return takes[0] if takes else None

    def set_active_take(self, take_group_id: str, clip_id: str) -> None:
        """Set which take is active (plays back) in a group.

        Deactivates all other takes in the group.
        """
        takes = self.get_takes_for_group(take_group_id)
        for t in takes:
            t.is_comp_active = (str(getattr(t, 'id', '')) == str(clip_id))
        log.info("Active take set to '%s' in group '%s'", clip_id, take_group_id)

    def add_take_to_group(self, take_group_id: str, clip: 'Clip',
                          make_active: bool = True) -> None:
        """Add a clip as a new take in an existing group.

        The new take gets the next take_index and optionally becomes active.
        """
        takes = self.get_takes_for_group(take_group_id)
        next_idx = max((int(getattr(t, 'take_index', 0)) for t in takes), default=-1) + 1

        clip.take_group_id = str(take_group_id)
        clip.take_index = int(next_idx)

        if make_active:
            # Deactivate all others
            for t in takes:
                t.is_comp_active = False
            clip.is_comp_active = True
        else:
            clip.is_comp_active = False

        log.info("Added take %d to group '%s' (clip '%s', active=%s)",
                 next_idx, take_group_id, getattr(clip, 'id', '?'), make_active)

    def delete_take(self, clip_id: str) -> Optional[str]:
        """Delete a take from its group. Returns the take_group_id or None.

        If the deleted take was active, the previous take becomes active.
        Does NOT delete the actual clip from the project — caller must do that.
        """
        if not self._project:
            return None
        try:
            clips = list(self._project.ctx.project.clips or [])
            target = None
            for c in clips:
                if str(getattr(c, 'id', '')) == str(clip_id):
                    target = c
                    break
            if not target:
                return None

            gid = getattr(target, 'take_group_id', '')
            if not gid:
                return None

            was_active = bool(getattr(target, 'is_comp_active', False))

            # Remove from project
            self._project.ctx.project.clips = [
                c for c in clips if str(getattr(c, 'id', '')) != str(clip_id)
            ]

            # If it was active, activate another take
            if was_active:
                remaining = self.get_takes_for_group(gid)
                if remaining:
                    remaining[-1].is_comp_active = True

            log.info("Deleted take '%s' from group '%s'", clip_id, gid)
            return gid
        except Exception as e:
            log.error("Failed to delete take: %s", e)
            return None

    def rename_take(self, clip_id: str, label: str) -> None:
        """Rename a take clip."""
        if not self._project:
            return
        try:
            for c in self._project.ctx.project.clips:
                if str(getattr(c, 'id', '')) == str(clip_id):
                    c.label = str(label)
                    break
        except Exception:
            pass

    def get_take_count(self, take_group_id: str) -> int:
        """Get number of takes in a group."""
        return len(self.get_takes_for_group(take_group_id))

    # ──────────────────────────────────────────────────────
    # Flatten (Comp → Single Clip)
    # ──────────────────────────────────────────────────────

    def flatten_take_group(self, take_group_id: str) -> Optional[str]:
        """Flatten a take group: keep only the active take, remove others.

        The active take loses its take_group_id and becomes a normal clip.

        Returns:
            clip_id of the flattened clip, or None on failure.
        """
        if not self._project:
            return None
        try:
            active = self.get_active_take(take_group_id)
            if not active:
                log.warning("No active take in group '%s'", take_group_id)
                return None

            active_id = str(getattr(active, 'id', ''))
            takes = self.get_takes_for_group(take_group_id)

            # Remove non-active takes from project
            remove_ids = {
                str(getattr(t, 'id', ''))
                for t in takes
                if str(getattr(t, 'id', '')) != active_id
            }

            if remove_ids:
                self._project.ctx.project.clips = [
                    c for c in self._project.ctx.project.clips
                    if str(getattr(c, 'id', '')) not in remove_ids
                ]

            # Clear take metadata from the surviving clip
            active.take_group_id = ""
            active.take_index = 0
            active.is_comp_active = True

            log.info("Flattened take group '%s': kept '%s', removed %d takes",
                     take_group_id, active_id, len(remove_ids))
            return active_id
        except Exception as e:
            log.error("Failed to flatten take group: %s", e)
            return None

    # ──────────────────────────────────────────────────────
    # Track take-lane visibility
    # ──────────────────────────────────────────────────────

    def toggle_take_lanes(self, track_id: str) -> bool:
        """Toggle take-lane visibility for a track.

        Returns:
            New visibility state.
        """
        if not self._project:
            return False
        try:
            for t in self._project.ctx.project.tracks:
                if str(getattr(t, 'id', '')) == str(track_id):
                    current = bool(getattr(t, 'take_lanes_visible', False))
                    t.take_lanes_visible = not current
                    return t.take_lanes_visible
        except Exception:
            pass
        return False

    def has_takes(self, track_id: str) -> bool:
        """Check if a track has any take groups."""
        return len(self.get_take_groups_for_track(track_id)) > 0

    # ──────────────────────────────────────────────────────
    # v0.0.20.640: Comp-Tool (AP2 Phase 2D)
    # ──────────────────────────────────────────────────────

    def set_comp_region(self, track_id: str, start_beat: float,
                        end_beat: float, source_clip_id: str,
                        crossfade_beats: float = 0.0) -> None:
        """Set a comp region: use audio from source_clip_id for the given beat range.

        If an existing region overlaps, it is split/trimmed to accommodate
        the new region (non-destructive, last-write-wins).

        Args:
            track_id: Track to comp on.
            start_beat: Region start in beats.
            end_beat: Region end in beats.
            source_clip_id: Clip ID of the take to use.
            crossfade_beats: Crossfade length at boundaries.
        """
        if not self._project:
            return
        try:
            track = self._find_track(track_id)
            if not track:
                return

            start_beat = float(start_beat)
            end_beat = max(start_beat + 0.25, float(end_beat))

            regions = list(getattr(track, 'comp_regions', []) or [])

            # Remove regions fully inside the new one
            regions = [
                r for r in regions
                if not (float(r.get('start_beat', 0)) >= start_beat
                        and float(r.get('end_beat', 0)) <= end_beat)
            ]

            # Trim regions that partially overlap
            trimmed = []
            for r in regions:
                rs = float(r.get('start_beat', 0))
                re = float(r.get('end_beat', 0))

                if re <= start_beat or rs >= end_beat:
                    # No overlap
                    trimmed.append(r)
                elif rs < start_beat and re > end_beat:
                    # New region is inside existing → split into two
                    trimmed.append({
                        'start_beat': rs,
                        'end_beat': start_beat,
                        'source_clip_id': r.get('source_clip_id', ''),
                        'crossfade_beats': r.get('crossfade_beats', 0.0),
                    })
                    trimmed.append({
                        'start_beat': end_beat,
                        'end_beat': re,
                        'source_clip_id': r.get('source_clip_id', ''),
                        'crossfade_beats': r.get('crossfade_beats', 0.0),
                    })
                elif rs < start_beat:
                    # Trim right side
                    trimmed.append({
                        'start_beat': rs,
                        'end_beat': start_beat,
                        'source_clip_id': r.get('source_clip_id', ''),
                        'crossfade_beats': r.get('crossfade_beats', 0.0),
                    })
                elif re > end_beat:
                    # Trim left side
                    trimmed.append({
                        'start_beat': end_beat,
                        'end_beat': re,
                        'source_clip_id': r.get('source_clip_id', ''),
                        'crossfade_beats': r.get('crossfade_beats', 0.0),
                    })

            # Add the new region
            trimmed.append({
                'start_beat': start_beat,
                'end_beat': end_beat,
                'source_clip_id': str(source_clip_id),
                'crossfade_beats': float(crossfade_beats),
            })

            # Sort by start_beat
            trimmed.sort(key=lambda r: float(r.get('start_beat', 0)))

            track.comp_regions = trimmed
            log.info("Comp region set on track '%s': beats %.2f–%.2f → clip '%s'",
                     track_id, start_beat, end_beat, source_clip_id)
        except Exception as e:
            log.error("Failed to set comp region: %s", e)

    def get_comp_regions(self, track_id: str) -> List[dict]:
        """Get all comp regions for a track, sorted by start_beat."""
        track = self._find_track(track_id)
        if not track:
            return []
        regions = list(getattr(track, 'comp_regions', []) or [])
        regions.sort(key=lambda r: float(r.get('start_beat', 0)))
        return regions

    def clear_comp_regions(self, track_id: str) -> None:
        """Remove all comp regions from a track."""
        track = self._find_track(track_id)
        if track:
            track.comp_regions = []
            log.info("Cleared comp regions on track '%s'", track_id)

    def get_active_clip_at_beat(self, track_id: str, beat: float) -> Optional[str]:
        """Get which clip_id should play at a given beat position.

        Checks comp_regions first (specific sections), then falls back
        to the globally active take.

        Returns:
            clip_id or None.
        """
        # Check comp regions
        regions = self.get_comp_regions(track_id)
        for r in regions:
            if float(r.get('start_beat', 0)) <= beat < float(r.get('end_beat', 0)):
                return str(r.get('source_clip_id', ''))

        # Fallback: find all take groups on this track and return the active take
        groups = self.get_take_groups_for_track(track_id)
        for gid, takes in groups.items():
            for t in takes:
                s = float(getattr(t, 'start_beats', 0))
                e = s + float(getattr(t, 'length_beats', 0))
                if s <= beat < e and getattr(t, 'is_comp_active', False):
                    return str(getattr(t, 'id', ''))
        return None

    def comp_select_take_at(self, track_id: str, take_clip_id: str) -> None:
        """Convenience: select an entire take as a comp region covering its full range.

        This is the simplest comp operation: click a take → it becomes
        active for its entire beat range.
        """
        if not self._project:
            return
        try:
            clip = None
            for c in self._project.ctx.project.clips:
                if str(getattr(c, 'id', '')) == str(take_clip_id):
                    clip = c
                    break
            if not clip:
                return
            start = float(getattr(clip, 'start_beats', 0))
            length = float(getattr(clip, 'length_beats', 4))
            self.set_comp_region(track_id, start, start + length, take_clip_id)
        except Exception as e:
            log.error("comp_select_take_at failed: %s", e)

    def _find_track(self, track_id: str) -> Optional['Track']:
        """Helper: find track by ID."""
        if not self._project:
            return None
        try:
            for t in self._project.ctx.project.tracks:
                if str(getattr(t, 'id', '')) == str(track_id):
                    return t
        except Exception:
            pass
        return None
