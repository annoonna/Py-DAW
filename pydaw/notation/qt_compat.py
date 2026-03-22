"""Qt Compatibility Shim - PySide6 zu PyQt6 Konverter.

ChronoScaleStudio verwendet PySide6, PyDAW verwendet PyQt6.
Dieser Shim macht beide kompatibel durch Monkey-Patching.
"""

import sys

# Versuche zuerst PyQt6 (DAW Standard)
try:
    from PyQt6 import QtWidgets, QtCore, QtGui
    from PyQt6.QtCore import pyqtSignal as Signal, pyqtSlot as Slot
    from PyQt6.QtWidgets import *
    from PyQt6.QtCore import *
    from PyQt6.QtGui import *
    
    QT_BACKEND = "PyQt6"
    
    # MONKEY-PATCHES für PySide6-Kompatibilität
    
    # QPainter RenderHints
    if not hasattr(QPainter, 'Antialiasing'):
        QPainter.Antialiasing = QPainter.RenderHint.Antialiasing
        QPainter.TextAntialiasing = QPainter.RenderHint.TextAntialiasing
        QPainter.SmoothPixmapTransform = QPainter.RenderHint.SmoothPixmapTransform
    
    # Qt Alignment
    if not hasattr(Qt, 'AlignLeft'):
        Qt.AlignLeft = Qt.AlignmentFlag.AlignLeft
        Qt.AlignRight = Qt.AlignmentFlag.AlignRight
        Qt.AlignTop = Qt.AlignmentFlag.AlignTop
        Qt.AlignBottom = Qt.AlignmentFlag.AlignBottom
        Qt.AlignCenter = Qt.AlignmentFlag.AlignCenter
        Qt.AlignHCenter = Qt.AlignmentFlag.AlignHCenter
        Qt.AlignVCenter = Qt.AlignmentFlag.AlignVCenter
    
    # Qt ScrollBarPolicy
    if not hasattr(Qt, 'ScrollBarAlwaysOn'):
        Qt.ScrollBarAlwaysOn = Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        Qt.ScrollBarAlwaysOff = Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        Qt.ScrollBarAsNeeded = Qt.ScrollBarPolicy.ScrollBarAsNeeded
    
    # Qt MouseButtons
    if not hasattr(Qt, 'LeftButton'):
        Qt.LeftButton = Qt.MouseButton.LeftButton
        Qt.RightButton = Qt.MouseButton.RightButton
        Qt.MiddleButton = Qt.MouseButton.MiddleButton
        Qt.NoButton = Qt.MouseButton.NoButton
    
    # Qt KeyboardModifiers
    if not hasattr(Qt, 'ControlModifier'):
        Qt.ControlModifier = Qt.KeyboardModifier.ControlModifier
        Qt.ShiftModifier = Qt.KeyboardModifier.ShiftModifier
        Qt.AltModifier = Qt.KeyboardModifier.AltModifier
        Qt.MetaModifier = Qt.KeyboardModifier.MetaModifier
        Qt.NoModifier = Qt.KeyboardModifier.NoModifier
    
    # Qt Keys  
    if not hasattr(Qt, 'Key_Escape'):
        Qt.Key_Escape = Qt.Key.Key_Escape
        Qt.Key_Delete = Qt.Key.Key_Delete
        Qt.Key_Backspace = Qt.Key.Key_Backspace
        Qt.Key_Return = Qt.Key.Key_Return
        Qt.Key_Enter = Qt.Key.Key_Enter
        Qt.Key_Space = Qt.Key.Key_Space
        Qt.Key_Tab = Qt.Key.Key_Tab
        Qt.Key_A = Qt.Key.Key_A
        Qt.Key_C = Qt.Key.Key_C
        Qt.Key_V = Qt.Key.Key_V
        Qt.Key_X = Qt.Key.Key_X
        Qt.Key_Z = Qt.Key.Key_Z
        Qt.Key_Y = Qt.Key.Key_Y
    
    # Qt GlobalColors (WICHTIG!)
    if not hasattr(Qt, 'black'):
        Qt.black = Qt.GlobalColor.black
        Qt.white = Qt.GlobalColor.white
        Qt.darkGray = Qt.GlobalColor.darkGray
        Qt.gray = Qt.GlobalColor.gray
        Qt.lightGray = Qt.GlobalColor.lightGray
        Qt.red = Qt.GlobalColor.red
        Qt.green = Qt.GlobalColor.green
        Qt.blue = Qt.GlobalColor.blue
        Qt.cyan = Qt.GlobalColor.cyan
        Qt.magenta = Qt.GlobalColor.magenta
        Qt.yellow = Qt.GlobalColor.yellow
        Qt.darkRed = Qt.GlobalColor.darkRed
        Qt.darkGreen = Qt.GlobalColor.darkGreen
        Qt.darkBlue = Qt.GlobalColor.darkBlue
        Qt.darkCyan = Qt.GlobalColor.darkCyan
        Qt.darkMagenta = Qt.GlobalColor.darkMagenta
        Qt.darkYellow = Qt.GlobalColor.darkYellow
        Qt.transparent = Qt.GlobalColor.transparent
    
    # QGraphicsView Anchors
    try:
        if not hasattr(QGraphicsView, 'AnchorUnderMouse'):
            QGraphicsView.AnchorUnderMouse = QGraphicsView.ViewportAnchor.AnchorUnderMouse
            QGraphicsView.NoAnchor = QGraphicsView.ViewportAnchor.NoAnchor
            QGraphicsView.AnchorViewCenter = QGraphicsView.ViewportAnchor.AnchorViewCenter
    except:
        pass
    
    # Qt PenStyle
    if not hasattr(Qt, 'SolidLine'):
        Qt.SolidLine = Qt.PenStyle.SolidLine
        Qt.DashLine = Qt.PenStyle.DashLine
        Qt.DotLine = Qt.PenStyle.DotLine
        Qt.DashDotLine = Qt.PenStyle.DashDotLine
        Qt.DashDotDotLine = Qt.PenStyle.DashDotDotLine
        Qt.NoPen = Qt.PenStyle.NoPen
    
    # Qt BrushStyle
    if not hasattr(Qt, 'SolidPattern'):
        Qt.SolidPattern = Qt.BrushStyle.SolidPattern
        Qt.NoBrush = Qt.BrushStyle.NoBrush
    
    # Qt CursorShape
    if not hasattr(Qt, 'ArrowCursor'):
        Qt.ArrowCursor = Qt.CursorShape.ArrowCursor
        Qt.CrossCursor = Qt.CursorShape.CrossCursor
        Qt.PointingHandCursor = Qt.CursorShape.PointingHandCursor
        Qt.SizeAllCursor = Qt.CursorShape.SizeAllCursor
    
    # Qt Orientation
    if not hasattr(Qt, 'Horizontal'):
        Qt.Horizontal = Qt.Orientation.Horizontal
        Qt.Vertical = Qt.Orientation.Vertical
    
    # AUTOMATIC FALLBACK für alle anderen Enums
    # Wenn ein Attribut nicht existiert, suche es automatisch in den Enum-Klassen
    _original_getattr = Qt.__getattribute__
    
    def _qt_getattr_fallback(self, name):
        """Automatischer Fallback für fehlende Qt-Enums."""
        try:
            return _original_getattr(self, name)
        except AttributeError:
            # Suche in häufigen Enum-Klassen
            for enum_class_name in [
                'AlignmentFlag', 'ScrollBarPolicy', 'MouseButton', 'KeyboardModifier',
                'Key', 'GlobalColor', 'PenStyle', 'BrushStyle', 'CursorShape',
                'Orientation', 'FocusPolicy', 'WindowType', 'ToolButtonStyle',
                'CheckState', 'ItemFlag', 'SortOrder', 'DockWidgetArea',
                'Corner', 'LayoutDirection', 'DateFormat', 'TimeSpec',
            ]:
                try:
                    enum_class = getattr(Qt, enum_class_name)
                    if hasattr(enum_class, name):
                        value = getattr(enum_class, name)
                        # Cache es für nächstes Mal
                        setattr(Qt, name, value)
                        return value
                except AttributeError:
                    continue
            
            # Nicht gefunden - originalen Fehler werfen
            raise AttributeError(f"type object 'Qt' has no attribute '{name}'")
    
    # Monkey-patch __getattribute__
    try:
        Qt.__class__.__getattribute__ = _qt_getattr_fallback
        print("[qt_compat] ✓ Automatischer Enum-Fallback aktiviert")
    except:
        pass  # Fallback failed - nicht schlimm
    
    print(f"[qt_compat] {QT_BACKEND} gepatcht für PySide6-Style")
    
except ImportError:
    # Fallback auf PySide6
    try:
        from PySide6 import QtWidgets, QtCore, QtGui
        from PySide6.QtCore import Signal, Slot
        from PySide6.QtWidgets import *
        from PySide6.QtCore import *
        from PySide6.QtGui import *
        
        QT_BACKEND = "PySide6"
        print(f"[qt_compat] {QT_BACKEND} - nativ")
        
    except ImportError:
        raise ImportError("Weder PyQt6 noch PySide6 verfügbar!")

# Export für andere Module
__all__ = [
    'QtWidgets', 'QtCore', 'QtGui',
    'Signal', 'Slot',
    'QT_BACKEND',
    # Alle Qt-Klassen
    'QWidget', 'QMainWindow', 'QApplication',
    'QVBoxLayout', 'QHBoxLayout', 'QFormLayout',
    'QLabel', 'QPushButton', 'QToolButton', 'QMenu',
    'QComboBox', 'QSpinBox', 'QCheckBox', 'QDoubleSpinBox',
    'QDialog', 'QDialogButtonBox', 'QMessageBox',
    'QGraphicsView', 'QGraphicsScene', 'QGraphicsItem',
    'QGraphicsRectItem', 'QGraphicsEllipseItem', 'QGraphicsLineItem',
    'QGraphicsPathItem', 'QGraphicsTextItem',
    'QPainter', 'QPen', 'QBrush', 'QColor', 'QFont',
    'QPointF', 'QRectF', 'QLineF', 'QPainterPath',
    'QKeySequence', 'QPixmap',
    'Qt',
]
