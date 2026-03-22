"""Undo/Redo stack.

Design goals:
- Minimal, deterministic behavior.
- No Qt dependency (signals are handled by services).
- Command Pattern compatible with DAW workflows (batching, already-done pushes).

Pro-DAW-Style shortcuts are handled at the QAction layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol


class Command(Protocol):
    """A reversible operation."""

    @property
    def label(self) -> str:  # pragma: no cover
        ...

    def do(self) -> None:  # pragma: no cover
        ...

    def undo(self) -> None:  # pragma: no cover
        ...


@dataclass
class _Entry:
    cmd: Command


class UndoStack:
    """Simple linear undo stack (no branching)."""

    def __init__(self, max_depth: int = 200):
        self._max_depth = int(max_depth)
        self._entries: List[_Entry] = []
        # _index points to the next command to redo.
        # undo applies entries[_index-1], redo applies entries[_index].
        self._index: int = 0

    # --------- queries ---------

    def clear(self) -> None:
        self._entries.clear()
        self._index = 0

    def can_undo(self) -> bool:
        return self._index > 0

    def can_redo(self) -> bool:
        return self._index < len(self._entries)

    def undo_label(self) -> str:
        if not self.can_undo():
            return ""
        return getattr(self._entries[self._index - 1].cmd, "label", "") or ""

    def redo_label(self) -> str:
        if not self.can_redo():
            return ""
        return getattr(self._entries[self._index].cmd, "label", "") or ""

    # --------- mutation ---------

    def push(self, cmd: Command, *, already_done: bool = True) -> None:
        """Push a new command.

        already_done=True means the caller has already applied the change, so we only
        register it for undo/redo without calling cmd.do().
        """
        # Drop redo branch
        if self._index < len(self._entries):
            self._entries = self._entries[: self._index]

        if not already_done:
            cmd.do()

        self._entries.append(_Entry(cmd=cmd))
        self._index = len(self._entries)

        # Enforce max depth
        if len(self._entries) > self._max_depth:
            overflow = len(self._entries) - self._max_depth
            self._entries = self._entries[overflow:]
            self._index = max(0, self._index - overflow)

    def undo(self) -> None:
        if not self.can_undo():
            return
        self._index -= 1
        self._entries[self._index].cmd.undo()

    def redo(self) -> None:
        if not self.can_redo():
            return
        self._entries[self._index].cmd.do()
        self._index += 1
