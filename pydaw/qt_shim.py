"""
Qt Backend Shim — Automatische Umschaltung PySide6 ↔ PyQt6.

Wird EINMAL ganz am Anfang von main.py aufgerufen.
Danach funktionieren alle `from PySide6...` Imports automatisch
mit PyQt6 als Backend — ohne eine einzige Zeile in den 130 Dateien zu ändern.

Logik:
    macOS → PySide6 (für Nuitka .dmg Build)
    Linux → PyQt6 bevorzugt (bessere Performance), PySide6 Fallback
    Windows → PyQt6 bevorzugt, PySide6 Fallback

Warum:
    - PySide6 = Nuitka macOS-kompatibel (.dmg Build möglich)
    - PyQt6 = besserer Sound/Performance auf Linux (getestet, v729)
    - Ein Ordner, null Code-Änderungen, automatische Erkennung
"""

import importlib
import sys
import types

QT_BACKEND = None  # "PyQt6" or "PySide6"


def _try_pyside6() -> bool:
    """Try importing PySide6."""
    try:
        import PySide6  # noqa: F401
        return True
    except ImportError:
        return False


def _try_pyqt6() -> bool:
    """Try importing PyQt6."""
    try:
        import PyQt6  # noqa: F401
        return True
    except ImportError:
        return False


def _install_pyqt6_as_pyside6_shim():
    """Map all PySide6 module names to PyQt6 equivalents.
    
    After this, `from PySide6.QtWidgets import QWidget` actually imports
    from PyQt6.QtWidgets — transparently, no code changes needed.
    """
    import PyQt6
    from PyQt6 import QtWidgets, QtCore, QtGui

    # Core alias: pyqtSignal → Signal, pyqtSlot → Slot
    if not hasattr(QtCore, 'Signal'):
        QtCore.Signal = QtCore.pyqtSignal
    if not hasattr(QtCore, 'Slot'):
        QtCore.Slot = QtCore.pyqtSlot

    # QFileSystemModel: in PyQt6 it's in QtWidgets, PySide6 also QtWidgets
    # But the code has it in QtWidgets already (fixed in v733)

    # Register PyQt6 modules under PySide6 names
    sys.modules['PySide6'] = PyQt6
    sys.modules['PySide6.QtWidgets'] = QtWidgets
    sys.modules['PySide6.QtCore'] = QtCore
    sys.modules['PySide6.QtGui'] = QtGui

    # Patch differences: some classes are in different modules
    # QFileSystemModel: PyQt6=QtGui, PySide6=QtWidgets
    if hasattr(QtGui, 'QFileSystemModel') and not hasattr(QtWidgets, 'QFileSystemModel'):
        QtWidgets.QFileSystemModel = QtGui.QFileSystemModel

    # Optional modules
    _optional_modules = [
        'QtOpenGL', 'QtOpenGLWidgets', 'QtSvg', 'QtSvgWidgets',
        'QtMultimedia', 'QtNetwork', 'QtPrintSupport',
    ]
    for mod_name in _optional_modules:
        try:
            mod = importlib.import_module(f'PyQt6.{mod_name}')
            sys.modules[f'PySide6.{mod_name}'] = mod
        except ImportError:
            pass


def setup_qt_backend() -> str:
    """Detect and configure the Qt backend.
    
    Call this ONCE at the very start of main.py, BEFORE any Qt imports.
    
    Returns "PyQt6" or "PySide6".
    """
    global QT_BACKEND

    is_macos = sys.platform == "darwin"
    
    if is_macos:
        # macOS: PySide6 preferred (Nuitka .dmg support)
        if _try_pyside6():
            QT_BACKEND = "PySide6"
        elif _try_pyqt6():
            _install_pyqt6_as_pyside6_shim()
            QT_BACKEND = "PyQt6"
        else:
            raise ImportError("Weder PySide6 noch PyQt6 installiert!")
    else:
        # Linux / Windows: PyQt6 preferred (better performance)
        if _try_pyqt6():
            _install_pyqt6_as_pyside6_shim()
            QT_BACKEND = "PyQt6"
        elif _try_pyside6():
            QT_BACKEND = "PySide6"
        else:
            raise ImportError("Weder PyQt6 noch PySide6 installiert!")

    return QT_BACKEND
