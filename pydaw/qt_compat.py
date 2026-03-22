"""
Qt Compatibility Layer — PySide6 preferred, PyQt6 fallback.

Usage in ALL pydaw modules:
    from pydaw.qt_compat import QtWidgets, QtCore, QtGui, Signal, Slot, Qt

This module tries PySide6 first (needed for Nuitka macOS .dmg builds).
If PySide6 is not installed, it falls back to PyQt6 seamlessly.

API differences handled:
    - Signal → Signal
    - Slot → Slot  
    - Enum scoping (PyQt6 uses fully-scoped enums)
"""

import sys

# Try PySide6 first (preferred for Nuitka cross-platform)
try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import Signal, Slot, Qt, QTimer, QThread, QObject, QEvent, QPoint, QPointF, QSize, QSizeF, QRect, QRectF, QUrl, QMimeData, QByteArray, QBuffer, QIODevice, QProcess, QRegularExpression
    from PySide6.QtCore import QSettings, QStandardPaths, QDir, QFile, QFileInfo

    try:
        from PySide6 import QtOpenGL, QtOpenGLWidgets
    except ImportError:
        QtOpenGL = None
        QtOpenGLWidgets = None

    try:
        from PySide6 import QtMultimedia
    except ImportError:
        QtMultimedia = None

    try:
        from PySide6.QtSvg import QSvgRenderer
    except ImportError:
        QSvgRenderer = None

    try:
        from PySide6.QtSvgWidgets import QSvgWidget
    except ImportError:
        QSvgWidget = None

    QT_BACKEND = "PySide6"

except ImportError:
    # Fallback to PyQt6
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import Signal as Signal, Slot as Slot, Qt, QTimer, QThread, QObject, QEvent, QPoint, QPointF, QSize, QSizeF, QRect, QRectF, QUrl, QMimeData, QByteArray, QBuffer, QIODevice, QProcess, QRegularExpression
    from PySide6.QtCore import QSettings, QStandardPaths, QDir, QFile, QFileInfo

    try:
        from PySide6 import QtOpenGL, QtOpenGLWidgets
    except ImportError:
        QtOpenGL = None
        QtOpenGLWidgets = None

    try:
        from PySide6 import QtMultimedia
    except ImportError:
        QtMultimedia = None

    try:
        from PySide6.QtSvg import QSvgRenderer
    except ImportError:
        QSvgRenderer = None

    try:
        from PySide6.QtSvgWidgets import QSvgWidget
    except ImportError:
        QSvgWidget = None

    QT_BACKEND = "PyQt6"


# Connection type compatibility
# PySide6 uses Qt.ConnectionType.UniqueConnection
# PyQt6 uses Qt.ConnectionType.UniqueConnection (same)
# Both work the same way for this.

def get_backend() -> str:
    """Return 'PySide6' or 'PyQt6'."""
    return QT_BACKEND

def is_pyside6() -> bool:
    return QT_BACKEND == "PySide6"

def is_pyqt6() -> bool:
    return QT_BACKEND == "PyQt6"
