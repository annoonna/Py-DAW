#!/usr/bin/env python3
"""Patch Qt-Enums für PyQt6-Kompatibilität.

PyQt6 hat QPainter.RenderHint.Antialiasing
PySide6 hat QPainter.Antialiasing

Dieser Patch macht PyQt6-Code PySide6-kompatibel.
"""

def patch_qt():
    """Patche Qt-Module für Kompatibilität."""
    try:
        from PySide6.QtGui import QPainter
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QGraphicsView
        
        # Monkey-Patch QPainter für PySide6-Style
        if not hasattr(QPainter, 'Antialiasing'):
            QPainter.Antialiasing = QPainter.RenderHint.Antialiasing
            QPainter.TextAntialiasing = QPainter.RenderHint.TextAntialiasing
            QPainter.SmoothPixmapTransform = QPainter.RenderHint.SmoothPixmapTransform
        
        # Monkey-Patch Qt für PySide6-Style
        if not hasattr(Qt, 'AlignLeft'):
            Qt.AlignLeft = Qt.AlignmentFlag.AlignLeft
            Qt.AlignRight = Qt.AlignmentFlag.AlignRight
            Qt.AlignTop = Qt.AlignmentFlag.AlignTop
            Qt.AlignBottom = Qt.AlignmentFlag.AlignBottom
            Qt.AlignCenter = Qt.AlignmentFlag.AlignCenter
            Qt.AlignHCenter = Qt.AlignmentFlag.AlignHCenter
            Qt.AlignVCenter = Qt.AlignmentFlag.AlignVCenter
        
        if not hasattr(Qt, 'ScrollBarAlwaysOn'):
            Qt.ScrollBarAlwaysOn = Qt.ScrollBarPolicy.ScrollBarAlwaysOn
            Qt.ScrollBarAlwaysOff = Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            Qt.ScrollBarAsNeeded = Qt.ScrollBarPolicy.ScrollBarAsNeeded
        
        if not hasattr(Qt, 'LeftButton'):
            Qt.LeftButton = Qt.MouseButton.LeftButton
            Qt.RightButton = Qt.MouseButton.RightButton
            Qt.MiddleButton = Qt.MouseButton.MiddleButton
        
        if not hasattr(Qt, 'ControlModifier'):
            Qt.ControlModifier = Qt.KeyboardModifier.ControlModifier
            Qt.ShiftModifier = Qt.KeyboardModifier.ShiftModifier
            Qt.AltModifier = Qt.KeyboardModifier.AltModifier
            Qt.MetaModifier = Qt.KeyboardModifier.MetaModifier
        
        if not hasattr(Qt, 'Key_Escape'):
            # Alle Keys - das wäre zu viel, aber die wichtigsten:
            Qt.Key_Escape = Qt.Key.Key_Escape
            Qt.Key_Delete = Qt.Key.Key_Delete
            Qt.Key_Backspace = Qt.Key.Key_Backspace
            Qt.Key_Return = Qt.Key.Key_Return
            Qt.Key_Enter = Qt.Key.Key_Enter
            Qt.Key_Space = Qt.Key.Key_Space
        
        # GraphicsView Anchors
        if not hasattr(QGraphicsView, 'AnchorUnderMouse'):
            QGraphicsView.AnchorUnderMouse = QGraphicsView.ViewportAnchor.AnchorUnderMouse
            QGraphicsView.NoAnchor = QGraphicsView.ViewportAnchor.NoAnchor
            QGraphicsView.AnchorViewCenter = QGraphicsView.ViewportAnchor.AnchorViewCenter
        
        print("[qt_patch] ✓ PyQt6 erfolgreich gepatcht für PySide6-Kompatibilität")
        return True
        
    except ImportError:
        # PySide6 - kein Patch nötig
        print("[qt_patch] PySide6 erkannt - kein Patch nötig")
        return True
    except Exception as e:
        print(f"[qt_patch] ✗ Fehler beim Patchen: {e}")
        return False

# Auto-Patch beim Import
patch_qt()
