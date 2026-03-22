# ChronoScale – Musik-Datenmodell
# Fundament für Notation, Skalen, MIDI, Stimmung
# zeitlos, explizit, Bach-tauglich

from dataclasses import dataclass, field
from typing import List, Optional

# -------------------------
# NOTE
# -------------------------
@dataclass
class Note:
    pitch: int                 # MIDI-Note (z.B. 60 = C4)
    start: float               # Startzeit in Beats
    duration: float            # Dauer in Beats
    velocity: int = 64
    cent_offset: float = 0.0   # Mikrotonale Abweichung (Bach!)

    def __str__(self):
        return f"Note(pitch={self.pitch}, start={self.start}, dur={self.duration}, cent={self.cent_offset})"


# -------------------------
# MEASURE (TAKT)
# -------------------------
@dataclass
class Measure:
    number: int
    time_signature: tuple = (4, 4)
    notes: List[Note] = field(default_factory=list)

    def add_note(self, note: Note):
        self.notes.append(note)

    def __str__(self):
        return f"Measure {self.number} ({len(self.notes)} notes)"


# -------------------------
# SCORE (STÜCK)
# -------------------------
@dataclass
class Score:
    title: str = "Untitled"
    tempo: int = 120
    tuning_system: str = "12-TET"
    measures: List[Measure] = field(default_factory=list)

    def add_measure(self, measure: Measure):
        self.measures.append(measure)

    def all_notes(self) -> List[Note]:
        notes = []
        for m in self.measures:
            notes.extend(m.notes)
        return notes

    def __str__(self):
        return f"Score('{self.title}', {len(self.measures)} measures)"
