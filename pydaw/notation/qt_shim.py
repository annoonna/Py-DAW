"""Qt6 compatibility shim for ported PySide6-era code.

The ChronoScaleStudio notation editor code was originally written against
PySide6/Qt6 where a lot of enums were available as direct attributes
(e.g. Qt.LeftButton). In PyQt6 those moved into nested enums
(e.g. Qt.MouseButton.LeftButton).

This shim exposes the commonly used legacy attribute names so the ported
code stays readable and we only touch imports.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt as _Qt
from PyQt6.QtGui import QPainter as _QPainter, QKeySequence as _QKeySequence


class _QtShim:
    # nested enums
    MouseButton = _Qt.MouseButton
    MouseButtons = _Qt.MouseButton
    KeyboardModifier = _Qt.KeyboardModifier
    KeyboardModifiers = _Qt.KeyboardModifier
    ScrollBarPolicy = _Qt.ScrollBarPolicy
    AlignmentFlag = _Qt.AlignmentFlag
    GlobalColor = _Qt.GlobalColor
    CursorShape = _Qt.CursorShape
    Key = _Qt.Key

    # legacy direct names used by the notation modules
    LeftButton = _Qt.MouseButton.LeftButton
    RightButton = _Qt.MouseButton.RightButton
    MiddleButton = _Qt.MouseButton.MiddleButton

    NoButton = _Qt.MouseButton.NoButton

    ControlModifier = _Qt.KeyboardModifier.ControlModifier
    ShiftModifier = _Qt.KeyboardModifier.ShiftModifier
    AltModifier = _Qt.KeyboardModifier.AltModifier
    NoModifier = _Qt.KeyboardModifier.NoModifier

    ScrollBarAlwaysOn = _Qt.ScrollBarPolicy.ScrollBarAlwaysOn
    ScrollBarAsNeeded = _Qt.ScrollBarPolicy.ScrollBarAsNeeded
    ScrollBarAlwaysOff = _Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    # orientation
    Horizontal = _Qt.Orientation.Horizontal
    Vertical = _Qt.Orientation.Vertical

    # toolbutton styles
    ToolButtonIconOnly = _Qt.ToolButtonStyle.ToolButtonIconOnly
    ToolButtonTextBesideIcon = _Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    ToolButtonTextUnderIcon = _Qt.ToolButtonStyle.ToolButtonTextUnderIcon

    AlignLeft = _Qt.AlignmentFlag.AlignLeft
    AlignTop = _Qt.AlignmentFlag.AlignTop
    AlignHCenter = _Qt.AlignmentFlag.AlignHCenter
    AlignVCenter = _Qt.AlignmentFlag.AlignVCenter

    # pen/brush styles and modes
    DashLine = _Qt.PenStyle.DashLine
    NoPen = _Qt.PenStyle.NoPen
    NoBrush = _Qt.BrushStyle.NoBrush
    IgnoreAspectRatio = _Qt.AspectRatioMode.IgnoreAspectRatio
    SmoothTransformation = _Qt.TransformationMode.SmoothTransformation

    # keys (legacy direct names)
    Key_Left = _Qt.Key.Key_Left
    Key_Right = _Qt.Key.Key_Right
    Key_Up = _Qt.Key.Key_Up
    Key_Down = _Qt.Key.Key_Down
    Key_Delete = _Qt.Key.Key_Delete
    Key_Backspace = _Qt.Key.Key_Backspace
    Key_Plus = _Qt.Key.Key_Plus
    Key_Minus = _Qt.Key.Key_Minus
    Key_Equal = _Qt.Key.Key_Equal
    Key_Z = _Qt.Key.Key_Z

    # colors
    transparent = _Qt.GlobalColor.transparent
    black = _Qt.GlobalColor.black
    white = _Qt.GlobalColor.white
    red = _Qt.GlobalColor.red
    yellow = _Qt.GlobalColor.yellow
    blue = _Qt.GlobalColor.blue
    gray = _Qt.GlobalColor.gray
    darkGray = _Qt.GlobalColor.darkGray
    lightGray = _Qt.GlobalColor.lightGray
    cyan = _Qt.GlobalColor.cyan
    darkCyan = _Qt.GlobalColor.darkCyan

    # cursors
    OpenHandCursor = _Qt.CursorShape.OpenHandCursor
    ClosedHandCursor = _Qt.CursorShape.ClosedHandCursor
    CrossCursor = _Qt.CursorShape.CrossCursor
    IBeamCursor = _Qt.CursorShape.IBeamCursor
    ArrowCursor = _Qt.CursorShape.ArrowCursor


    def __getattr__(self, name: str):
        """Fallback resolver for legacy enum attributes.

        The original code accessed many enums as Qt.<Name>. In PyQt6 those moved
        to nested enums. We try a few common buckets to keep the notation module
        compatible without touching every call site.
        """
        # direct attribute on Qt (rare)
        if hasattr(_Qt, name):
            return getattr(_Qt, name)

        # Try nested enum groups
        buckets = [
            _Qt.GlobalColor,
            _Qt.PenStyle,
            _Qt.BrushStyle,
            _Qt.AspectRatioMode,
            _Qt.TransformationMode,
            _Qt.Key,
            _Qt.CursorShape,
            _Qt.MouseButton,
            _Qt.KeyboardModifier,
            _Qt.ScrollBarPolicy,
            _Qt.ToolButtonStyle,
            _Qt.AlignmentFlag,
        ]
        for b in buckets:
            if hasattr(b, name):
                return getattr(b, name)
        raise AttributeError(f"{self.__class__.__name__!s} object has no attribute {name!r}")

Qt = _QtShim()


class QPainter:
    # legacy renderhint name
    Antialiasing = _QPainter.RenderHint.Antialiasing


class QKeySequence:
    # legacy standard keys
    Copy = _QKeySequence.StandardKey.Copy
    Cut = _QKeySequence.StandardKey.Cut
    Paste = _QKeySequence.StandardKey.Paste
    Undo = _QKeySequence.StandardKey.Undo
    Redo = _QKeySequence.StandardKey.Redo
    Delete = _QKeySequence.StandardKey.Delete
