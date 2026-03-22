"""Arranger Keyboard Handler - Standard DAW Shortcuts.

v0.0.20.142 (Arranger Freeze Fix):
- Ctrl+V pastes at the *current playhead* (instead of always at beat 0)
- Multi-clip paste is now *batched* (no per-note UI update spam)
- MIDI notes are copied in bulk (deepcopy list) -> prevents GUI freezes
- Optional grid snapping: Ctrl+V snaps to grid, Ctrl+Shift+V disables snap
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable
import copy

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QKeyEvent

if TYPE_CHECKING:
    from pydaw.services.project_service import ProjectService


class ArrangerKeyboardHandler(QObject):
    """Handles all keyboard shortcuts for Arranger canvas."""
    
    # Signals
    status_message = pyqtSignal(str, int)  # (message, timeout_ms)
    request_update = pyqtSignal()  # Request canvas repaint
    
    def __init__(
        self,
        project: ProjectService,
        *,
        get_playhead_beat: Callable[[], float] | None = None,
        get_snap_beats: Callable[[], float] | None = None,
    ):
        super().__init__()
        self.project = project
        self._clipboard_clips: list[dict] = []  # Internal clipboard

        # Context providers injected by ArrangerCanvas.
        self._get_playhead_beat = get_playhead_beat
        self._get_snap_beats = get_snap_beats

    def set_context(
        self,
        *,
        get_playhead_beat: Callable[[], float] | None = None,
        get_snap_beats: Callable[[], float] | None = None,
    ) -> None:
        """Inject/refresh Arranger context providers (playhead + snap grid)."""
        if get_playhead_beat is not None:
            self._get_playhead_beat = get_playhead_beat
        if get_snap_beats is not None:
            self._get_snap_beats = get_snap_beats
    
    def handle_key_press(
        self,
        event: QKeyEvent,
        selected_clip_ids: set[str],
        selected_clip_id: str,
    ) -> bool:
        """Handle key press event.
        
        Returns:
            True if event was handled, False otherwise
        """
        key = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        
        # Avoid heavy console spam (can stall UI on some terminals)
        
        # Ctrl+C: Copy
        if ctrl and key == Qt.Key.Key_C:
            self._copy_clips(selected_clip_ids)
            return True
        
        # Ctrl+V: Paste
        elif ctrl and key == Qt.Key.Key_V:
            # Ctrl+Shift+V disables snap
            self._paste_clips(disable_snap=shift)
            return True
        
        # Ctrl+X: Cut
        elif ctrl and key == Qt.Key.Key_X:
            self._cut_clips(selected_clip_ids)
            return True
        
        # Ctrl+D: Duplicate
        elif ctrl and key == Qt.Key.Key_D:
            self._duplicate_clips(selected_clip_ids)
            return True
        
        # Ctrl+J: Join/Consolidate
        elif ctrl and key == Qt.Key.Key_J:
            # Pro variants:
            # Ctrl+J = Consolidate (snap to grid)
            # Shift+Ctrl+J = Trim (no snapping)
            # Alt+Ctrl+J = Consolidate + Handles
            mode = 'default'
            if shift and alt:
                mode = 'trim_handles'
            elif shift:
                mode = 'trim'
            elif alt:
                mode = 'handles'
            self._join_clips(selected_clip_ids, mode=mode)
            return True
        
        # Ctrl+Z: Undo
        elif ctrl and key == Qt.Key.Key_Z:
            self._undo()
            return True
        
        # Ctrl+Y or Ctrl+Shift+Z: Redo
        elif ctrl and (key == Qt.Key.Key_Y or (shift and key == Qt.Key.Key_Z)):
            self._redo()
            return True
        
        # Ctrl+A: Select All
        elif ctrl and key == Qt.Key.Key_A:
            self._select_all_clips()
            return True
        
        # Delete: Delete selected clips
        elif key == Qt.Key.Key_Delete or key == Qt.Key.Key_Backspace:
            self._delete_clips(selected_clip_ids)
            return True
        
        # Escape: Deselect all
        elif key == Qt.Key.Key_Escape:
            selected_clip_ids.clear()
            self.request_update.emit()
            self.status_message.emit("Auswahl aufgehoben", 1000)
            return True
        
        return False
    
    def _copy_clips(self, selected_clip_ids: set[str]) -> None:
        """Copy selected clips to clipboard."""
        if not selected_clip_ids:
            self.status_message.emit("Keine Clips ausgewählt", 2000)
            return

        import copy

        self._clipboard_clips = []
        clips = list(self.project.ctx.project.clips)
        for clip in clips:
            if str(getattr(clip, "id", "")) not in selected_clip_ids:
                continue

            clip_data: dict = {"clip": copy.deepcopy(clip)}

            # Copy MIDI notes (bulk) if MIDI clip
            if str(getattr(clip, "kind", "")) == "midi":
                try:
                    clip_data["midi_notes"] = copy.deepcopy(self.project.ctx.project.midi_notes.get(clip.id, []))
                except Exception:
                    clip_data["midi_notes"] = []

            self._clipboard_clips.append(clip_data)

        count = len(self._clipboard_clips)
        self.status_message.emit(f"{count} Clip(s) kopiert", 2000)
    
    def _paste_clips(self, *, disable_snap: bool = False) -> None:
        """Paste clips from clipboard."""
        if not self._clipboard_clips:
            self.status_message.emit("Zwischenablage ist leer", 2000)
            return

        import copy
        from pydaw.model.project import Clip, new_id
        from pydaw.model.midi import MidiNote

        # Determine target beat (playhead)
        playhead = 0.0
        try:
            if self._get_playhead_beat is not None:
                playhead = float(self._get_playhead_beat() or 0.0)
        except Exception:
            playhead = 0.0

        # Optional snap
        snap_beats = 0.0
        try:
            if (not disable_snap) and self._get_snap_beats is not None:
                snap_beats = float(self._get_snap_beats() or 0.0)
        except Exception:
            snap_beats = 0.0

        def _snap(v: float) -> float:
            try:
                g = float(snap_beats)
                if g > 0.0:
                    return max(0.0, round(float(v) / g) * g)
            except Exception:
                pass
            return max(0.0, float(v))

        playhead = _snap(playhead)

        # Find earliest clip start in clipboard to calculate offset
        try:
            min_start = min(float(getattr(c["clip"], "start_beats", 0.0)) for c in self._clipboard_clips)
        except Exception:
            min_start = 0.0
        offset = float(playhead) - float(min_start)

        pasted_ids: list[str] = []
        new_clips: list[Clip] = []

        # Build all clips first (batch) to avoid repeated UI refresh and freezes.
        for item in self._clipboard_clips:
            src = item.get("clip")
            if src is None:
                continue

            try:
                src_kind = str(getattr(src, "kind", "audio"))
                src_track = str(getattr(src, "track_id", ""))
                src_start = float(getattr(src, "start_beats", 0.0))

                new_start = _snap(src_start + offset)

                # Deepcopy the whole clip so audio params/automation/warp markers survive.
                dup = copy.deepcopy(src)
                dup.id = new_id("clip")
                dup.start_beats = float(new_start)
                dup.track_id = str(src_track)

                # Label: keep readable, but mark copies once
                try:
                    base_label = str(getattr(dup, "label", ""))
                    if base_label and (not base_label.endswith(" Copy")):
                        dup.label = base_label + " Copy"
                except Exception:
                    pass

                new_clips.append(dup)
                pasted_ids.append(str(dup.id))

                # MIDI notes: bulk-copy list (NO per-note emit)
                if src_kind == "midi":
                    notes = item.get("midi_notes", [])
                    if notes:
                        try:
                            fixed: list[MidiNote] = []
                            for n in notes:
                                if isinstance(n, MidiNote):
                                    fixed.append(copy.deepcopy(n))
                                elif isinstance(n, dict):
                                    fixed.append(
                                        MidiNote(
                                            pitch=int(n.get("pitch", 60)),
                                            start_beats=float(n.get("start_beats", 0.0)),
                                            length_beats=float(n.get("length_beats", 1.0)),
                                            velocity=int(n.get("velocity", 100)),
                                        )
                                    )
                            self.project.ctx.project.midi_notes[str(dup.id)] = fixed
                        except Exception:
                            self.project.ctx.project.midi_notes[str(dup.id)] = []
                    else:
                        self.project.ctx.project.midi_notes[str(dup.id)] = []

            except Exception:
                continue

        # Commit batch to project model
        if not new_clips:
            self.status_message.emit("Nichts eingefügt", 2000)
            return

        try:
            self.project.ctx.project.clips.extend(new_clips)
        except Exception:
            for c in new_clips:
                try:
                    self.project.ctx.project.clips.append(c)
                except Exception:
                    pass

        # Select last pasted clip (single update)
        try:
            last_id = str(pasted_ids[-1])
            self.project.ctx.project.selected_clip_id = last_id
            try:
                self.project._active_clip_id = last_id  # keep UI compatibility
            except Exception:
                pass
            try:
                self.project.clip_selected.emit(last_id)
                self.project.active_clip_changed.emit(last_id)
            except Exception:
                pass
        except Exception:
            pass

        # One project refresh
        try:
            self.project._emit_updated()
        except Exception:
            try:
                self.project.project_updated.emit()
            except Exception:
                pass

        self.request_update.emit()
        self.status_message.emit(f"{len(pasted_ids)} Clip(s) eingefügt", 2000)
    
    def _cut_clips(self, selected_clip_ids: set[str]) -> None:
        """Cut selected clips (copy + delete)."""
        if not selected_clip_ids:
            self.status_message.emit("Keine Clips ausgewählt", 2000)
            return
        
        # Copy first
        self._copy_clips(selected_clip_ids)
        
        # Then delete
        self._delete_clips(selected_clip_ids)
        
        self.status_message.emit(f"{len(self._clipboard_clips)} Clip(s) ausgeschnitten", 2000)
    
    def _duplicate_clips(self, selected_clip_ids: set[str]) -> None:
        """Duplicate selected clips HORIZONTALLY (to the right).
        
        FIXED v0.0.19.7.4: Mit " Copy" Suffix wie eine Pro-DAW!
        """
        if not selected_clip_ids:
            self.status_message.emit("Keine Clips ausgewählt", 2000)
            return
        
        new_ids = []
        clips = self.project.ctx.project.clips
        
        for clip_id in selected_clip_ids:
            try:
                # Find original clip
                clip = next((c for c in clips if c.id == clip_id), None)
                if not clip:
                    continue
                
                # Calculate new position: directly after original clip (to the RIGHT!)
                new_start = float(clip.start_beats) + float(clip.length_beats)
                
                # Generate label with " Copy" suffix
                original_label = str(getattr(clip, "label", ""))
                if original_label.endswith(" Copy"):
                    # Already a copy, keep adding
                    new_label = original_label
                else:
                    new_label = f"{original_label} Copy"
                
                # Create duplicate based on type
                if clip.kind == "midi":
                    new_id = self.project.add_midi_clip_at(
                        str(clip.track_id),  # SAME track!
                        start_beats=new_start,  # Directly to the right! ✅
                        length_beats=float(clip.length_beats),
                        label=new_label  # With " Copy" suffix! ✅
                    )
                    
                    # Copy ALL MIDI notes
                    notes = self.project.ctx.project.midi_notes.get(clip.id, [])
                    for note in notes:
                        self.project.add_note(
                            new_id,
                            pitch=int(note.pitch),
                            start_beats=float(note.start_beats),
                            length_beats=float(note.length_beats),
                            velocity=int(note.velocity)
                        )
                    
                    new_ids.append(new_id)
                
                elif clip.kind == "audio":
                    # FIXED v0.0.19.7.6: source_path statt audio_file_path
                    audio_path = str(getattr(clip, "source_path", ""))
                    if audio_path:
                        new_id = self.project.add_audio_clip_from_file_at(
                            str(clip.track_id),  # SAME track!
                            audio_path,
                            start_beats=new_start  # Directly to the right! ✅
                        )
                        
                        # Rename with " Copy" suffix
                        if new_id:
                            new_clip = next((c for c in self.project.ctx.project.clips if c.id == new_id), None)
                            if new_clip:
                                new_clip.label = new_label  # With " Copy" suffix! ✅
                        
                        new_ids.append(new_id)
                
            except Exception as e:
                print(f"[KeyboardHandler._duplicate_clips] Error duplicating clip {clip_id}: {e}")
                import traceback
                # traceback.print_exc()
        
        # Select duplicated clips
        selected_clip_ids.clear()
        selected_clip_ids.update(new_ids)
        
        count = len(new_ids)
        self.request_update.emit()
        self.status_message.emit(f"{count} Clip(s) nach rechts dupliziert", 2000)
    
    def _join_clips(self, selected_clip_ids: set[str], *, mode: str = 'default', delete_originals: bool = True) -> None:
        """Join/Consolidate selected clips."""
        if len(selected_clip_ids) < 2:
            self.status_message.emit("Mindestens 2 Clips zum Verbinden auswählen", 2000)
            return
        
        try:
            # Get all selected clips
            clips = [c for c in self.project.ctx.project.clips if c.id in selected_clip_ids]
            
            # Must be on same track
            track_ids = {c.track_id for c in clips}
            if len(track_ids) > 1:
                self.status_message.emit("Clips müssen auf gleicher Spur sein", 2000)
                return
            
            # Must be same kind
            kinds = {c.kind for c in clips}
            if len(kinds) > 1:
                self.status_message.emit("Nur MIDI- oder Audio-Clips verbinden", 2000)
                return
            
            # Sort by start position
            clips.sort(key=lambda c: float(c.start_beats))
            
            # Calculate joined clip bounds
            start = float(clips[0].start_beats)
            end = max(float(c.start_beats) + float(c.length_beats) for c in clips)
            length = end - start
            
            # Create new joined clip
            track_id = clips[0].track_id
            kind = clips[0].kind
            
            if kind == "midi":
                new_id = self.project.add_midi_clip_at(
                    track_id,
                    start_beats=start,
                    length_beats=length,
                    label="Joined Clip",
                )
                
                # Copy all MIDI notes from all clips
                for clip in clips:
                    notes = self.project.ctx.project.midi_notes.get(clip.id, [])
                    for note in notes:
                        # Adjust note position relative to joined clip while preserving
                        # per-note expressions/curve types/notation metadata.
                        note_copy = copy.deepcopy(note)
                        note_copy.start_beats = float(getattr(note, "start_beats", 0.0)) + (float(clip.start_beats) - start)
                        self.project.add_midi_note(new_id, note_copy.clamp())
                
                # Delete original clips
                for clip in clips:
                    self.project.delete_clip(clip.id)
                
                # Select new clip
                selected_clip_ids.clear()
                selected_clip_ids.add(new_id)
                
                self.request_update.emit()
                self.status_message.emit(f"{len(clips)} Clips verbunden", 2000)
            
            else:
                # Audio-Clips: Bounce/Consolidate (Ctrl+J) -> eine neue durchgehende WAV + ein Clip.
                try:
                    snap = None
                    if self._get_snap_beats is not None:
                        try:
                            snap = float(self._get_snap_beats() or 0.0)
                        except Exception:
                            snap = None
                    new_id = None
                    if hasattr(self.project, 'consolidate_audio_clips_bounce'):
                        handles = 0.125 if mode in ('handles', 'trim_handles') else 0.0
                        snap_to_grid = False if mode in ('trim', 'trim_handles') else True
                        new_id = self.project.consolidate_audio_clips_bounce(
                            list(selected_clip_ids),
                            snap_beats=snap,
                            snap_to_grid=bool(snap_to_grid),
                            handles_beats=float(handles),
                            tail_beats=0.0,
                            normalize=False,
                            delete_originals=bool(delete_originals),
                            label="Consolidated Audio",
                        )
                    if new_id:
                        selected_clip_ids.clear()
                        selected_clip_ids.add(str(new_id))
                        self.request_update.emit()
                        self.status_message.emit(f"{len(clips)} Audio-Clips zusammengefügt", 2000)
                    else:
                        self.status_message.emit("Audio-Consolidate fehlgeschlagen (Auswahl/Render)", 2500)
                except Exception as e:
                    print(f"Error joining audio clips: {e}")
                    self.status_message.emit("Audio-Consolidate Fehler", 2500)
        
        except Exception as e:
            print(f"Error joining clips: {e}")
            self.status_message.emit(f"Fehler beim Verbinden: {e}", 3000)
    
    def _delete_clips(self, selected_clip_ids: set[str]) -> None:
        """Delete selected clips."""
        if not selected_clip_ids:
            self.status_message.emit("Keine Clips ausgewählt", 2000)
            return
        
        count = len(selected_clip_ids)
        for clip_id in list(selected_clip_ids):
            try:
                self.project.delete_clip(clip_id)
            except Exception as e:
                print(f"Error deleting clip {clip_id}: {e}")
        
        selected_clip_ids.clear()
        self.request_update.emit()
        self.status_message.emit(f"{count} Clip(s) gelöscht", 2000)
    
    def _select_all_clips(self) -> None:
        """Select all clips in project."""
        # This will be handled by the canvas
        self.status_message.emit("Alle Clips ausgewählt", 1000)
    
    def _undo(self) -> None:
        """Undo last action."""
        # Placeholder - full undo system would be implemented separately
        self.status_message.emit("Undo (noch nicht implementiert)", 2000)
    
    def _redo(self) -> None:
        """Redo last undone action."""
        # Placeholder - full redo system would be implemented separately
        self.status_message.emit("Redo (noch nicht implementiert)", 2000)
