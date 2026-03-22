"""Undoable full-project snapshot edits.

Safety-first fallback for broad project-level undo/redo coverage.
It stores before/after snapshots as plain JSON-safe dicts and restores them
through a callback owned by ProjectService.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict


ProjectSnapshot = Dict[str, Any]


@dataclass
class ProjectSnapshotEditCommand:
    """Replace the whole project model with before/after snapshots."""

    before: ProjectSnapshot
    after: ProjectSnapshot
    label: str
    apply_snapshot: Callable[[ProjectSnapshot], None]

    def do(self) -> None:
        self.apply_snapshot(self.after)

    def undo(self) -> None:
        self.apply_snapshot(self.before)
