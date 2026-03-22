"""Undoable MIDI note edits.

We store note lists as lightweight snapshots (list of dicts) to avoid
index instability and keep commands deterministic.

The actual application of a snapshot is delegated to a callback so this
module remains free of service/UI imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Dict

# Snapshot dicts are JSON-safe note representations.
# v0.0.20.196: may include nested structures (e.g. per-note expressions).
MidiSnapshot = List[Dict[str, Any]]


@dataclass
class MidiNotesEditCommand:
    """Replaces a clip's MIDI note list with before/after snapshots."""

    clip_id: str
    before: MidiSnapshot
    after: MidiSnapshot
    label: str
    apply_snapshot: Callable[[str, MidiSnapshot], None]

    def do(self) -> None:
        self.apply_snapshot(self.clip_id, self.after)

    def undo(self) -> None:
        self.apply_snapshot(self.clip_id, self.before)
