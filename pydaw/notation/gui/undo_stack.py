
# ChronoScaleStudio – Undo/Redo Stack (Snapshot-basiert)
# Robust und einfach: wir speichern Zustände als serialisierte Dicts.
# Design: 1) kein Diff-Fehler-Risiko 2) später erweiterbar (Command-Pattern möglich)

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any, List, Optional


@dataclass
class _Snapshot:
    state: dict


class UndoStack:
    def __init__(self, get_state: Callable[[], dict], set_state: Callable[[dict], None], max_depth: int = 200):
        self._get_state = get_state
        self._set_state = set_state
        self._max_depth = max(10, int(max_depth))
        self._stack: List[_Snapshot] = []
        self._index: int = -1
        self._blocked: bool = False

    def reset(self):
        self._stack.clear()
        self._index = -1

    def init(self):
        """Initialen Zustand setzen (nach App-Start oder Projekt-Load)."""
        self.reset()
        self.push_checkpoint()

    def push_checkpoint(self):
        """Aktuellen Zustand als neuen Checkpoint speichern (löscht Redo-Branch)."""
        if self._blocked:
            return
        state = self._get_state()
        # Redo-Branch abschneiden
        if self._index < len(self._stack) - 1:
            self._stack = self._stack[: self._index + 1]
        self._stack.append(_Snapshot(state=state))
        # Depth limit
        if len(self._stack) > self._max_depth:
            drop = len(self._stack) - self._max_depth
            self._stack = self._stack[drop:]
        self._index = len(self._stack) - 1

    def can_undo(self) -> bool:
        return self._index > 0

    def can_redo(self) -> bool:
        return 0 <= self._index < (len(self._stack) - 1)

    def undo(self) -> bool:
        if not self.can_undo():
            return False
        self._index -= 1
        self._apply_index()
        return True

    def redo(self) -> bool:
        if not self.can_redo():
            return False
        self._index += 1
        self._apply_index()
        return True

    def _apply_index(self):
        if not (0 <= self._index < len(self._stack)):
            return
        try:
            self._blocked = True
            self._set_state(self._stack[self._index].state)
        finally:
            self._blocked = False
