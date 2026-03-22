"""Editor Focus Context — Dual-Clock Datenobjekte.

Dieses Modul definiert die Datenstrukturen für die Entkopplung von
Clip-Launcher-Looping und Arranger-Timeline (Dual-Clock-System).

Phase A: Reine Datenstruktur, kein Verhaltenswechsel.

Kernkonzept:
    Ein ``EditorFocusContext`` beschreibt VOLLSTÄNDIG, was gerade editiert
    wird und in welchem Kontext — Arranger oder Launcher.

    Ein ``LauncherSlotRuntimeState`` ist ein GUI-sicherer Snapshot des
    aktuellen Playback-Zustands eines Launcher-Slots.

Design-Referenz: DUAL_CLOCK_CLIP_LAUNCHER_ARRANGER_DESIGN.md §5

v0.0.20.612 — 2026-03-19 — Phase A: Datenobjekte
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass(frozen=True)
class EditorFocusContext:
    """Beschreibt was gerade editiert wird und in welchem Kontext.

    Wird emittiert über ``ClipContextService.editor_focus_changed``.

    Attributes:
        source: ``"arranger"`` oder ``"launcher"`` — woher der Fokus kommt.
        clip_id: ID des aktiven Clips.
        slot_key: Launcher-Slot-Key (z.B. ``"scene:0:track:abc123"``).
            Bei ``source="launcher"`` Pflicht, bei ``source="arranger"`` None.
        scene_index: Scene-Index im Launcher (0-basiert), oder None.
        track_id: Track-ID, oder None.
        arranger_clip_start_beats: Start-Beat des Clips im Arranger (0.0 für Launcher-Clips).
        clip_length_beats: Gesamtlänge des Clips in Beats.
        loop_start_beats: Loop-Start innerhalb des Clips.
        loop_end_beats: Loop-End innerhalb des Clips.
        pinned_to_slot: Wenn True, bleibt der Editor bei Follow-Actions
            auf diesem Slot (empfohlenes Default für erste Implementierung).
    """
    source: Literal["arranger", "launcher"]
    clip_id: str
    slot_key: Optional[str] = None
    scene_index: Optional[int] = None
    track_id: Optional[str] = None
    arranger_clip_start_beats: float = 0.0
    clip_length_beats: float = 4.0
    loop_start_beats: float = 0.0
    loop_end_beats: float = 4.0
    pinned_to_slot: bool = True

    @property
    def is_launcher(self) -> bool:
        """Kommt der Fokus aus dem Launcher?"""
        return self.source == "launcher"

    @property
    def is_arranger(self) -> bool:
        """Kommt der Fokus aus dem Arranger?"""
        return self.source == "arranger"

    @property
    def loop_span(self) -> float:
        """Loop-Spanne in Beats (mindestens 0.001 um Division-by-Zero zu vermeiden)."""
        return max(0.001, self.loop_end_beats - self.loop_start_beats)


@dataclass
class LauncherSlotRuntimeState:
    """GUI-sicherer Snapshot des aktiven Playback-Zustands eines Slots.

    Wird von ``ClipLauncherPlaybackService.get_runtime_snapshot()`` erzeugt.

    WICHTIG: Dieser State darf NICHT direkt aus dem Audio-Thread live benutzt
    werden, sondern nur als unter Lock kopierter Snapshot.

    Attributes:
        slot_key: Launcher-Slot-Key.
        clip_id: ID des zugehörigen Clips.
        is_playing: Slot spielt gerade.
        is_queued: Slot ist gequeued (wartet auf Launch-Quantize).
        voice_start_beat: Globaler Beat bei dem die aktuelle Voice gestartet wurde.
            None wenn nicht spielend.
        local_beat: Aktuelle lokale Position innerhalb des Loops.
        loop_start_beats: Loop-Start des Slots.
        loop_end_beats: Loop-End des Slots.
        loop_count: Wie oft der Loop bisher durchgelaufen ist.
        track_id: Track-ID des Slots.
    """
    slot_key: str
    clip_id: str
    is_playing: bool = False
    is_queued: bool = False
    voice_start_beat: Optional[float] = None
    local_beat: float = 0.0
    loop_start_beats: float = 0.0
    loop_end_beats: float = 4.0
    loop_count: int = 0
    track_id: str = ""

    @property
    def loop_span(self) -> float:
        """Loop-Spanne in Beats."""
        return max(0.001, self.loop_end_beats - self.loop_start_beats)

    def compute_local_beat(self, global_beat: float) -> float:
        """Berechne lokale Beat-Position aus globalem Beat.

        Dies ist die zentrale Formel für Launcher-Fokus:
            local = loop_start + (global_beat - voice_start_beat) % loop_span

        Args:
            global_beat: Aktueller globaler Transport-Beat.

        Returns:
            Lokale Beat-Position innerhalb des Loops.
        """
        if self.voice_start_beat is None:
            return self.local_beat
        span = self.loop_span
        elapsed = max(0.0, global_beat - self.voice_start_beat)
        return self.loop_start_beats + (elapsed % span)
