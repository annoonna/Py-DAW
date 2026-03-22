#!/usr/bin/env python3
"""Fixe relative Imports zu absolute Imports."""

import re
from pathlib import Path

def fix_imports(filepath: Path):
    """Fixe Imports in einer Datei."""
    try:
        content = filepath.read_text(encoding='utf-8')
        original = content
        
        # Ersetze relative Imports
        # from music.xxx import -> from pydaw.notation.music.xxx import
        content = re.sub(
            r'^from music\.([^\s]+) import',
            r'from pydaw.notation.music.\1 import',
            content,
            flags=re.MULTILINE
        )
        
        # from gui.xxx import -> from pydaw.notation.gui.xxx import
        content = re.sub(
            r'^from gui\.([^\s]+) import',
            r'from pydaw.notation.gui.\1 import',
            content,
            flags=re.MULTILINE
        )
        
        # from audio.xxx import -> from pydaw.notation.audio.xxx import
        content = re.sub(
            r'^from audio\.([^\s]+) import',
            r'from pydaw.notation.audio.\1 import',
            content,
            flags=re.MULTILINE
        )
        
        # from scales.xxx import -> from pydaw.notation.scales.xxx import
        content = re.sub(
            r'^from scales\.([^\s]+) import',
            r'from pydaw.notation.scales.\1 import',
            content,
            flags=re.MULTILINE
        )
        
        # from midi.xxx import -> from pydaw.notation.midi.xxx import
        content = re.sub(
            r'^from midi\.([^\s]+) import',
            r'from pydaw.notation.midi.\1 import',
            content,
            flags=re.MULTILINE
        )
        
        if content != original:
            filepath.write_text(content, encoding='utf-8')
            print(f"✓ Fixed: {filepath.name}")
            return True
        return False
        
    except Exception as e:
        print(f"✗ Error: {filepath}: {e}")
        return False

def main():
    notation_dir = Path(__file__).parent
    fixed = 0
    
    for py_file in notation_dir.rglob("*.py"):
        if py_file.name.startswith("fix_") or py_file.name.startswith("convert_"):
            continue
        if fix_imports(py_file):
            fixed += 1
    
    print(f"\n✓ Fixed {fixed} files")

if __name__ == "__main__":
    main()
