
# ChronoScaleStudio – Track Model (Spuren)
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Clef = Literal["treble", "bass"]


@dataclass
class Track:
    id: int
    name: str
    clef: Clef = "treble"
    midi_channel: int = 0
    mute: bool = False
    solo: bool = False

    @property
    def clef_symbol(self) -> str:
        return "𝄞" if self.clef == "treble" else "𝄢"
