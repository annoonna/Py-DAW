
# ChronoScaleStudio – Notations-/Sequenz-Events
# Einheitliches Datenmodell für Noten, Pausen und Haltebögen.
# Erweiterung: track_id (Spuren), default=1

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Literal


EventType = Literal["note", "rest"]


@dataclass
class BaseEvent:
    id: int
    start: float        # Startzeit in Beats
    duration: float     # Dauer in Beats
    track_id: int = 1   # Spur-ID (1..n)

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass
class NoteEvent(BaseEvent):
    pitch: int = 60            # MIDI-Pitch (0–127)
    velocity: int = 90          # 1–127
    tie_to_next: bool = False   # Haltebogen zur nächsten Note (gleiche Tonhöhe, direkt anschließend)

    @property
    def type(self) -> EventType:
        return "note"


@dataclass
class RestEvent(BaseEvent):
    @property
    def type(self) -> EventType:
        return "rest"
