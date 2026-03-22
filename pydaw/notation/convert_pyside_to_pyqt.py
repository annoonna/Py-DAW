#!/usr/bin/env python3
"""Konvertiere PySide6 Imports zu PyQt6-kompatibel.

Ersetzt alle PySide6-Imports durch qt_compat Import.
"""

import re
from pathlib import Path

def convert_file(filepath: Path):
    """Konvertiere eine einzelne Datei."""
    try:
        content = filepath.read_text(encoding='utf-8')
        original = content
        
        # Ersetze PySide6 Imports durch qt_compat
        # Pattern 1: from PySide6.QtWidgets import ...
        content = re.sub(
            r'from PySide6\.QtWidgets import ([^\n]+)',
            r'from pydaw.notation.qt_compat import \1',
            content
        )
        
        # Pattern 2: from PySide6.QtCore import ...
        content = re.sub(
            r'from PySide6\.QtCore import ([^\n]+)',
            r'from pydaw.notation.qt_compat import \1',
            content
        )
        
        # Pattern 3: from PySide6.QtGui import ...
        content = re.sub(
            r'from PySide6\.QtGui import ([^\n]+)',
            r'from pydaw.notation.qt_compat import \1',
            content
        )
        
        # Pattern 4: from PySide6 import ...
        content = re.sub(
            r'from PySide6 import ([^\n]+)',
            r'from pydaw.notation import qt_compat',
            content
        )
        
        # Pattern 5: import PySide6...
        content = re.sub(
            r'import PySide6',
            r'from pydaw.notation import qt_compat',
            content
        )
        
        # Nur schreiben wenn geändert
        if content != original:
            filepath.write_text(content, encoding='utf-8')
            print(f"✓ Konvertiert: {filepath}")
            return True
        else:
            print(f"  Keine Änderung: {filepath}")
            return False
            
    except Exception as e:
        print(f"✗ Fehler bei {filepath}: {e}")
        return False

def main():
    """Hauptfunktion."""
    notation_dir = Path(__file__).parent
    
    print(f"Konvertiere PySide6 → PyQt6 in: {notation_dir}")
    print("=" * 60)
    
    converted = 0
    total = 0
    
    # Durchsuche alle .py Dateien
    for py_file in notation_dir.rglob("*.py"):
        if py_file.name == "convert_pyside_to_pyqt.py":
            continue  # Skip this script
        
        total += 1
        if convert_file(py_file):
            converted += 1
    
    print("=" * 60)
    print(f"Fertig! {converted}/{total} Dateien konvertiert.")

if __name__ == "__main__":
    main()
