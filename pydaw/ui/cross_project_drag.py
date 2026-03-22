"""Cross-Project Drag & Drop (v0.0.20.77).

Handles drag-and-drop of tracks, clips, and groups between project tabs.
Implements Full State Transfer: device chains, automations, routing preserved.

Drag data is serialized as JSON in a custom MIME type:
  application/x-pydaw-cross-project

The drag payload contains:
  - source_tab_index: int
  - item_type: "tracks" | "clips"
  - track_ids / clip_ids: list[str]
  - include_device_chains: bool

Drop targets (ArrangerView, TrackList) check for this MIME type
and delegate to ProjectTabService.copy_tracks_between_tabs().
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QMimeData

# Custom MIME type for cross-project drag operations
MIME_CROSS_PROJECT = "application/x-pydaw-cross-project"


def create_track_drag_data(
    source_tab_index: int,
    track_ids: List[str],
    include_clips: bool = True,
    include_device_chains: bool = True,
) -> QMimeData:
    """Create MIME data for dragging tracks between project tabs."""
    payload = {
        "source_tab_index": source_tab_index,
        "item_type": "tracks",
        "track_ids": track_ids,
        "include_clips": include_clips,
        "include_device_chains": include_device_chains,
    }
    mime = QMimeData()
    mime.setData(MIME_CROSS_PROJECT, json.dumps(payload).encode("utf-8"))
    # Also set plain text for debugging
    names = ", ".join(track_ids)
    mime.setText(f"PyDAW Tracks: {names}")
    return mime


def create_clip_drag_data(
    source_tab_index: int,
    clip_ids: List[str],
) -> QMimeData:
    """Create MIME data for dragging clips between project tabs."""
    payload = {
        "source_tab_index": source_tab_index,
        "item_type": "clips",
        "clip_ids": clip_ids,
    }
    mime = QMimeData()
    mime.setData(MIME_CROSS_PROJECT, json.dumps(payload).encode("utf-8"))
    names = ", ".join(clip_ids)
    mime.setText(f"PyDAW Clips: {names}")
    return mime


def parse_cross_project_drop(mime_data: QMimeData) -> Optional[Dict[str, Any]]:
    """Parse cross-project drag data from a drop event.

    Returns None if the MIME data doesn't contain cross-project data.
    Returns the parsed payload dict otherwise.
    """
    if not mime_data.hasFormat(MIME_CROSS_PROJECT):
        return None
    try:
        raw = bytes(mime_data.data(MIME_CROSS_PROJECT)).decode("utf-8")
        return json.loads(raw)
    except Exception:
        return None


def is_cross_project_drag(mime_data: QMimeData) -> bool:
    """Check if a drag event contains cross-project data."""
    return mime_data.hasFormat(MIME_CROSS_PROJECT)
