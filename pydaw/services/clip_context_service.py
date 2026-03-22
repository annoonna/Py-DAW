"""Clip Context Service - Zentrale Verwaltung des aktiven Slot-Kontexts.

Koordiniert:
- Aktiven Slot/Clip für alle Editoren
- Broadcast zu Piano-Roll, Notation, Sampler
- Loop-Parameter Sync
- Event-Editing Context
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from pydaw.services.editor_focus import EditorFocusContext

if TYPE_CHECKING:
    from pydaw.services.project_service import ProjectService
    from pydaw.model.project import AudioClip, MidiClip


class ClipContextService(QObject):
    """Service zur Verwaltung des aktiven Clip-Kontexts.
    
    Wenn ein Slot im Clip-Launcher angeklickt wird, wird dieser Service
    benachrichtigt und broadcastet den neuen Kontext an alle interessierten
    Editoren (Piano-Roll, Notation, Sampler, Audio Event Editor).
    
    Signals:
        active_slot_changed: (scene_idx, track_id, clip_id) - Neuer aktiver Slot
        loop_params_changed: (clip_id, start, end, offset) - Loop-Parameter geändert
        slot_edit_requested: (clip_id) - Slot soll editiert werden (z.B. Doppelklick)
    """
    
    # Signals
    active_slot_changed = Signal(int, str, str)  # scene_idx, track_id, clip_id
    loop_params_changed = Signal(str, float, float, float)  # clip_id, start, end, offset
    slot_edit_requested = Signal(str)  # clip_id
    # v0.0.20.612: Dual-Clock Phase A — neues Signal für reicheren Kontext
    editor_focus_changed = Signal(object)  # EditorFocusContext
    
    def __init__(self, project_service: ProjectService):
        super().__init__()
        self.project = project_service
        
        # Aktueller Kontext
        self._active_scene_idx: int = 0
        self._active_track_id: str = ""
        self._active_clip_id: str = ""
        # v0.0.20.612: Dual-Clock Phase A — EditorFocusContext
        self._editor_focus: EditorFocusContext | None = None
        
    def set_active_slot(
        self,
        scene_idx: int,
        track_id: str,
        clip_id: str = ""
    ) -> None:
        """Setze aktiven Slot.
        
        Args:
            scene_idx: Scene-Index (0-basiert)
            track_id: Track-ID
            clip_id: Clip-ID (kann leer sein wenn Slot leer)
        """
        # State updaten
        old_clip = self._active_clip_id
        self._active_scene_idx = int(scene_idx)
        self._active_track_id = str(track_id)
        self._active_clip_id = str(clip_id)
        
        # Broadcast
        self.active_slot_changed.emit(scene_idx, track_id, clip_id)
        
        # Wenn Clip geändert -> auch ProjectService benachrichtigen
        if clip_id and clip_id != old_clip:
            self.project.set_active_clip(clip_id)
            
    def get_active_slot(self) -> tuple[int, str, str]:
        """Aktueller Slot zurückgeben.
        
        Returns:
            (scene_idx, track_id, clip_id)
        """
        return (self._active_scene_idx, self._active_track_id, self._active_clip_id)
        
    def get_active_clip(self) -> AudioClip | MidiClip | None:
        """Aktiven Clip zurückgeben."""
        if not self._active_clip_id:
            return None
        return self.project.get_clip(self._active_clip_id)
        
    def update_loop_params(
        self,
        clip_id: str,
        start: float,
        end: float,
        offset: float
    ) -> None:
        """Loop-Parameter für Clip updaten.
        
        Args:
            clip_id: Clip-ID
            start: Loop-Start (Beats)
            end: Loop-End (Beats)
            offset: Offset (Beats)
        """
        clip = self.project.get_clip(clip_id)
        if not clip:
            return
            
        # Clip-Attribute updaten
        clip.loop_start = float(start)
        clip.loop_end = float(end)
        clip.offset = float(offset)
        
        # Projekt als geändert markieren
        self.project.project_updated.emit()
        
        # Broadcast
        self.loop_params_changed.emit(clip_id, start, end, offset)
        
    def request_slot_edit(self, clip_id: str) -> None:
        """Request Edit-Modus für Slot (z.B. nach Doppelklick).
        
        Öffnet den passenden Editor:
        - Audio Clip -> AudioEventEditor
        - MIDI Clip -> Piano-Roll
        
        Args:
            clip_id: Clip-ID
        """
        self.slot_edit_requested.emit(clip_id)
        
    def open_loop_editor(self, clip_id: str) -> bool:
        """Öffne Loop-Editor Dialog für Clip.
        
        Args:
            clip_id: Clip-ID
            
        Returns:
            True wenn Dialog accepted, sonst False
        """
        clip = self.project.get_clip(clip_id)
        if not clip:
            return False
            
        # Import hier um zirkuläre Imports zu vermeiden
        from pydaw.ui.clip_slot_loop_editor import ClipSlotLoopEditor
        
        dialog = ClipSlotLoopEditor(clip)
        if dialog.exec() == dialog.DialogCode.Accepted:
            start, end, offset = dialog.get_loop_params()
            self.update_loop_params(clip_id, start, end, offset)
            return True
            
        return False
        
    def get_clip_loop_params(self, clip_id: str) -> tuple[float, float, float] | None:
        """Loop-Parameter für Clip abrufen.
        
        Args:
            clip_id: Clip-ID
            
        Returns:
            (start, end, offset) oder None wenn Clip nicht existiert
        """
        clip = self.project.get_clip(clip_id)
        if not clip:
            return None
            
        start = float(getattr(clip, 'loop_start', 0.0))
        end = float(getattr(clip, 'loop_end', getattr(clip, 'length_beats', 4.0)))
        offset = float(getattr(clip, 'offset', 0.0))
        
        return (start, end, offset)
        
    def clear_active_slot(self) -> None:
        """Aktiven Slot clearen."""
        self.set_active_slot(0, "", "")

    # ------------------------------------------------------------------
    # v0.0.20.612: Dual-Clock Phase A — EditorFocusContext-API
    # ------------------------------------------------------------------

    def set_editor_focus(self, ctx: EditorFocusContext) -> None:
        """Setze den EditorFocusContext und broadcaste an alle Editoren.

        Dies ist der NEUE Pfad für reicheren Kontext (Clip + Quelle + Slot + Runtime).
        Der alte ``active_slot_changed``-Pfad bleibt weiterhin parallel aktiv.

        Args:
            ctx: Vollständiger EditorFocusContext.
        """
        self._editor_focus = ctx
        self.editor_focus_changed.emit(ctx)

    def get_editor_focus(self) -> EditorFocusContext | None:
        """Aktuellen EditorFocusContext zurückgeben.

        Returns:
            Der aktuelle Fokuskontext, oder None wenn noch nicht gesetzt.
        """
        return self._editor_focus

    def build_arranger_focus(self, clip_id: str) -> EditorFocusContext | None:
        """Erzeuge einen EditorFocusContext für einen Arranger-Clip.

        Liest Clip-Daten aus dem Projekt und baut einen Kontext mit
        ``source="arranger"``.

        Args:
            clip_id: Clip-ID.

        Returns:
            EditorFocusContext oder None wenn Clip nicht existiert.
        """
        clip = self.project.get_clip(clip_id)
        if clip is None:
            return None
        try:
            track_id = str(getattr(clip, 'track_id', '') or '')
            start = float(getattr(clip, 'start_beats', 0.0) or 0.0)
            length = float(getattr(clip, 'length_beats', 4.0) or 4.0)
            ls = float(getattr(clip, 'loop_start_beats', 0.0) or 0.0)
            le = float(getattr(clip, 'loop_end_beats', 0.0) or 0.0)
            if le <= ls + 1e-6:
                le = length
            return EditorFocusContext(
                source="arranger",
                clip_id=str(clip_id),
                slot_key=None,
                scene_index=None,
                track_id=track_id,
                arranger_clip_start_beats=start,
                clip_length_beats=length,
                loop_start_beats=ls,
                loop_end_beats=le,
                pinned_to_slot=False,
            )
        except Exception:
            return None

    def build_launcher_focus(
        self,
        clip_id: str,
        slot_key: str,
        scene_index: int,
        track_id: str,
    ) -> EditorFocusContext | None:
        """Erzeuge einen EditorFocusContext für einen Launcher-Slot.

        Liest Clip-Daten aus dem Projekt und baut einen Kontext mit
        ``source="launcher"`` und dem zugehörigen ``slot_key``.

        Args:
            clip_id: Clip-ID.
            slot_key: Launcher-Slot-Key.
            scene_index: Scene-Index (0-basiert).
            track_id: Track-ID.

        Returns:
            EditorFocusContext oder None wenn Clip nicht existiert.
        """
        clip = self.project.get_clip(clip_id)
        if clip is None:
            return None
        try:
            length = float(getattr(clip, 'length_beats', 4.0) or 4.0)
            ls = float(getattr(clip, 'loop_start_beats', 0.0) or 0.0)
            le = float(getattr(clip, 'loop_end_beats', 0.0) or 0.0)
            if le <= ls + 1e-6:
                le = length
            return EditorFocusContext(
                source="launcher",
                clip_id=str(clip_id),
                slot_key=str(slot_key),
                scene_index=int(scene_index),
                track_id=str(track_id),
                arranger_clip_start_beats=0.0,
                clip_length_beats=length,
                loop_start_beats=ls,
                loop_end_beats=le,
                pinned_to_slot=True,
            )
        except Exception:
            return None
