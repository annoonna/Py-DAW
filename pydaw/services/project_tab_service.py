"""Multi-Project Tab Service (v0.0.20.77).

Manages multiple simultaneously open projects in tabs (Bitwig-Style).
Only the *active* project is connected to the audio engine at any time.
Inactive projects remain fully loaded in memory for instant switching.

Design:
  - Each open project is a ProjectTab with its own ProjectContext + UndoStack
  - Switching tabs: detach old project from audio, attach new one
  - Cross-project operations: copy tracks/clips between tabs
  - Resource-safe: only one audio engine active

Signals:
  tab_added(int)           - new tab created at index
  tab_removed(int)         - tab closed at index
  tab_switched(int, int)   - old_idx, new_idx
  tab_renamed(int, str)    - tab index, new display name
  tab_dirty_changed(int, bool)  - tab index, is_dirty
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from pydaw.fileio.file_manager import (
    ProjectContext,
    new_project as fm_new_project,
    open_project as fm_open_project,
    save_project_to as fm_save_project_to,
)
from pydaw.model.project import Project, Track, Clip, MediaItem
from pydaw.commands import UndoStack


@dataclass
class ProjectTab:
    """One open project in the tab bar."""
    ctx: ProjectContext
    undo_stack: UndoStack = field(default_factory=lambda: UndoStack(max_depth=400))
    dirty: bool = False
    # Cache the display name for fast access
    _display_name: str = ""

    @property
    def display_name(self) -> str:
        if self._display_name:
            return self._display_name
        if self.ctx.path:
            return self.ctx.path.stem.replace(".pydaw", "")
        return self.ctx.project.name or "Neues Projekt"

    @display_name.setter
    def display_name(self, value: str) -> None:
        self._display_name = value

    @property
    def project(self) -> Project:
        return self.ctx.project

    @property
    def path(self) -> Optional[Path]:
        return self.ctx.path


class ProjectTabService(QObject):
    """Manages multiple open project tabs.

    Only one project at a time is 'active' (connected to audio engine).
    This service coordinates switching, opening, closing, and cross-project ops.
    """

    tab_added = Signal(int)                  # index
    tab_removed = Signal(int)                # index
    tab_switched = Signal(int, int)          # old_idx, new_idx
    tab_renamed = Signal(int, str)           # index, name
    tab_dirty_changed = Signal(int, bool)    # index, dirty
    status = Signal(str)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._tabs: List[ProjectTab] = []
        self._active_idx: int = -1

    # --- Properties ---

    @property
    def tabs(self) -> List[ProjectTab]:
        return list(self._tabs)

    @property
    def active_index(self) -> int:
        return self._active_idx

    @property
    def active_tab(self) -> Optional[ProjectTab]:
        if 0 <= self._active_idx < len(self._tabs):
            return self._tabs[self._active_idx]
        return None

    @property
    def count(self) -> int:
        return len(self._tabs)

    def tab_at(self, idx: int) -> Optional[ProjectTab]:
        if 0 <= idx < len(self._tabs):
            return self._tabs[idx]
        return None

    # --- Tab Lifecycle ---

    def add_new_project(self, name: str = "Neues Projekt", activate: bool = True) -> int:
        """Create a new empty project in a new tab. Returns tab index."""
        ctx = fm_new_project(name)
        tab = ProjectTab(ctx=ctx)
        self._tabs.append(tab)
        idx = len(self._tabs) - 1
        self.tab_added.emit(idx)
        if activate:
            self.switch_to(idx)
        return idx

    def open_project_in_tab(self, path: Path, activate: bool = True) -> int:
        """Open a project file in a new tab. Returns tab index.

        If the project is already open in a tab, switches to that tab instead.
        """
        # Check if already open
        resolved = path.resolve()
        for i, tab in enumerate(self._tabs):
            if tab.path and tab.path.resolve() == resolved:
                if activate:
                    self.switch_to(i)
                self.status.emit(f"Projekt bereits geöffnet (Tab {i + 1}).")
                return i

        try:
            ctx = fm_open_project(path)
        except Exception as exc:
            self.error.emit(f"Fehler beim Öffnen: {exc}")
            return -1

        tab = ProjectTab(ctx=ctx)
        self._tabs.append(tab)
        idx = len(self._tabs) - 1
        self.tab_added.emit(idx)
        if activate:
            self.switch_to(idx)
        self.status.emit(f"Projekt geöffnet in Tab {idx + 1}: {tab.display_name}")
        return idx

    def close_tab(self, idx: int) -> bool:
        """Close a project tab. Returns True if closed.

        Does NOT prompt for save — caller (UI) should check dirty state first.
        """
        if idx < 0 or idx >= len(self._tabs):
            return False

        was_active = (idx == self._active_idx)
        self._tabs.pop(idx)
        self.tab_removed.emit(idx)

        # Adjust active index
        if was_active:
            if len(self._tabs) == 0:
                self._active_idx = -1
            elif idx >= len(self._tabs):
                self.switch_to(len(self._tabs) - 1)
            else:
                self.switch_to(idx)
        elif self._active_idx > idx:
            self._active_idx -= 1

        return True

    def switch_to(self, idx: int) -> bool:
        """Switch the active project tab. Returns True on success."""
        if idx < 0 or idx >= len(self._tabs):
            return False
        if idx == self._active_idx:
            return True

        old_idx = self._active_idx
        self._active_idx = idx
        self.tab_switched.emit(old_idx, idx)
        return True

    def mark_dirty(self, idx: int | None = None) -> None:
        """Mark a tab as having unsaved changes."""
        if idx is None:
            idx = self._active_idx
        tab = self.tab_at(idx)
        if tab and not tab.dirty:
            tab.dirty = True
            self.tab_dirty_changed.emit(idx, True)

    def mark_clean(self, idx: int | None = None) -> None:
        """Mark a tab as saved."""
        if idx is None:
            idx = self._active_idx
        tab = self.tab_at(idx)
        if tab and tab.dirty:
            tab.dirty = False
            self.tab_dirty_changed.emit(idx, False)

    def rename_tab(self, idx: int, name: str) -> None:
        """Set a custom display name for a tab."""
        tab = self.tab_at(idx)
        if tab:
            tab.display_name = name
            self.tab_renamed.emit(idx, name)

    # --- Save Operations ---

    def save_tab(self, idx: int | None = None, path: Path | None = None) -> bool:
        """Save a project tab. Returns True on success."""
        if idx is None:
            idx = self._active_idx
        tab = self.tab_at(idx)
        if not tab:
            return False

        save_path = path or tab.path
        if not save_path:
            self.error.emit("Kein Speicherpfad angegeben.")
            return False

        try:
            try:
                from pydaw.audio.vst3_host import embed_project_state_blobs
                embed_project_state_blobs(tab.ctx.project)
            except Exception:
                pass
            tab.ctx = fm_save_project_to(save_path, tab.ctx)
            tab.dirty = False
            self.tab_dirty_changed.emit(idx, False)
            self.tab_renamed.emit(idx, tab.display_name)
            self.status.emit(f"Projekt gespeichert: {save_path.name}")
            return True
        except Exception as exc:
            self.error.emit(f"Speichern fehlgeschlagen: {exc}")
            return False

    # --- Cross-Project Operations ---

    def copy_tracks_between_tabs(
        self,
        source_idx: int,
        target_idx: int,
        track_ids: List[str],
        include_clips: bool = True,
        include_device_chains: bool = True,
    ) -> List[str]:
        """Copy tracks (with optional clips + devices) from one tab to another.

        Returns list of new track IDs in the target project.
        Full State Transfer: device chains, automations, routing are preserved.
        """
        src = self.tab_at(source_idx)
        tgt = self.tab_at(target_idx)
        if not src or not tgt:
            return []

        src_proj = src.project
        tgt_proj = tgt.project
        new_track_ids: List[str] = []

        # Build lookup maps
        src_tracks = {t.id: t for t in src_proj.tracks}

        for tid in track_ids:
            src_track = src_tracks.get(tid)
            if not src_track:
                continue

            # Deep copy the track with a new ID
            from pydaw.model.project import new_id
            new_track = copy.deepcopy(src_track)
            old_id = new_track.id
            new_track.id = new_id("trk")
            new_track.name = f"{new_track.name} (kopiert)"

            if not include_device_chains:
                new_track.note_fx_chain = {"devices": []}
                new_track.audio_fx_chain = {"type": "chain", "mix": 1.0, "wet_gain": 1.0, "devices": []}
                new_track.instrument_state = {}

            tgt_proj.tracks.append(new_track)
            new_track_ids.append(new_track.id)

            if include_clips:
                # Copy clips belonging to this track
                for clip in src_proj.clips:
                    if clip.track_id != old_id:
                        continue
                    new_clip = copy.deepcopy(clip)
                    new_clip.id = new_id("clip")
                    new_clip.track_id = new_track.id
                    tgt_proj.clips.append(new_clip)

                    # Copy MIDI notes for this clip
                    src_notes = src_proj.midi_notes.get(clip.id, [])
                    if src_notes:
                        tgt_proj.midi_notes[new_clip.id] = copy.deepcopy(src_notes)

                    # Copy media references
                    if clip.media_id:
                        src_media = next(
                            (m for m in src_proj.media if m.id == clip.media_id), None
                        )
                        if src_media:
                            new_media = copy.deepcopy(src_media)
                            new_media.id = new_id("media")
                            tgt_proj.media.append(new_media)
                            new_clip.media_id = new_media.id

        if new_track_ids:
            self.mark_dirty(target_idx)
            self.status.emit(
                f"{len(new_track_ids)} Track(s) von Tab {source_idx + 1} → Tab {target_idx + 1} kopiert."
            )

        return new_track_ids

    def copy_clips_between_tabs(
        self,
        source_idx: int,
        target_idx: int,
        clip_ids: List[str],
        target_track_id: str,
    ) -> List[str]:
        """Copy specific clips from one tab to another, assigning to a target track.

        Returns list of new clip IDs in the target project.
        """
        src = self.tab_at(source_idx)
        tgt = self.tab_at(target_idx)
        if not src or not tgt:
            return []

        src_proj = src.project
        tgt_proj = tgt.project
        new_clip_ids: List[str] = []

        src_clips = {c.id: c for c in src_proj.clips}

        for cid in clip_ids:
            src_clip = src_clips.get(cid)
            if not src_clip:
                continue

            from pydaw.model.project import new_id
            new_clip = copy.deepcopy(src_clip)
            new_clip.id = new_id("clip")
            new_clip.track_id = target_track_id
            tgt_proj.clips.append(new_clip)
            new_clip_ids.append(new_clip.id)

            # MIDI notes
            src_notes = src_proj.midi_notes.get(cid, [])
            if src_notes:
                tgt_proj.midi_notes[new_clip.id] = copy.deepcopy(src_notes)

            # Media
            if src_clip.media_id:
                src_media = next(
                    (m for m in src_proj.media if m.id == src_clip.media_id), None
                )
                if src_media:
                    new_media = copy.deepcopy(src_media)
                    new_media.id = new_id("media")
                    tgt_proj.media.append(new_media)
                    new_clip.media_id = new_media.id

        if new_clip_ids:
            self.mark_dirty(target_idx)
            self.status.emit(
                f"{len(new_clip_ids)} Clip(s) von Tab {source_idx + 1} → Tab {target_idx + 1} kopiert."
            )

        return new_clip_ids

    # --- Project Peek (Browser Integration) ---

    @staticmethod
    def peek_project(path: Path) -> Optional[Dict[str, Any]]:
        """Load a project file read-only for browsing (without adding to tabs).

        Returns a dict with project metadata, tracks, and clip summaries.
        Useful for the file browser to show project contents without full load.
        """
        try:
            from pydaw.fileio.project_io import load_project
            proj = load_project(path)
            return {
                "name": proj.name,
                "version": proj.version,
                "bpm": proj.bpm,
                "time_signature": proj.time_signature,
                "tracks": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "kind": t.kind,
                        "plugin_type": t.plugin_type,
                        "sf2_path": t.sf2_path,
                    }
                    for t in proj.tracks
                ],
                "clips": [
                    {
                        "id": c.id,
                        "label": c.label,
                        "kind": c.kind,
                        "track_id": c.track_id,
                        "start_beats": c.start_beats,
                        "length_beats": c.length_beats,
                    }
                    for c in proj.clips
                ],
                "clip_count": len(proj.clips),
                "track_count": len(proj.tracks),
            }
        except Exception:
            return None

    # --- Tab Reorder ---

    def move_tab(self, from_idx: int, to_idx: int) -> None:
        """Move a tab from one position to another (drag reorder).

        Adjusts ``_active_idx`` so the same project stays active.
        """
        if from_idx == to_idx:
            return
        if not (0 <= from_idx < len(self._tabs)) or not (0 <= to_idx < len(self._tabs)):
            return
        tab = self._tabs.pop(from_idx)
        self._tabs.insert(to_idx, tab)
        # Keep active_idx pointing at the same tab
        if self._active_idx == from_idx:
            self._active_idx = to_idx
        elif from_idx < self._active_idx <= to_idx:
            self._active_idx -= 1
        elif to_idx <= self._active_idx < from_idx:
            self._active_idx += 1

    # --- Init helper for migrating existing single-project to tab system ---

    def adopt_existing_project(self, ctx: ProjectContext, undo_stack: UndoStack | None = None) -> int:
        """Adopt an already-loaded project (from the existing MainWindow) into the tab system.

        This is the migration path: the first project that was loaded by the old
        single-project code gets adopted as Tab 0.
        """
        tab = ProjectTab(
            ctx=ctx,
            undo_stack=undo_stack or UndoStack(max_depth=400),
        )
        self._tabs.append(tab)
        idx = len(self._tabs) - 1
        self._active_idx = idx
        self.tab_added.emit(idx)
        return idx
