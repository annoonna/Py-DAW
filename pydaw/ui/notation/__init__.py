"""Notation UI helpers (integrated / lightweight).

This package hosts reusable drawing utilities for staff-based notation.

It is separate from the larger experimental notation subsystem under
``pydaw/notation``. The goal here is to provide a *minimal, stable* renderer
that can be embedded inside the main DAW UI.
"""

from .staff_renderer import StaffRenderer, StaffStyle
from .notation_view import NotationView, NotationWidget
from .tools import DrawTool, EraseTool, NotationTool, SelectTool

__all__ = [
    "StaffRenderer",
    "StaffStyle",
    "NotationView",
    "NotationWidget",
    "NotationTool",
    "DrawTool",
    "EraseTool",
    "SelectTool",
]
