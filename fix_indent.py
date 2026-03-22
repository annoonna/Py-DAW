#!/usr/bin/env python3
"""Fix indentation in notation_view.py - all methods after line 528 need 4 spaces."""

import sys

def fix_indentation(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    fixed_lines = []
    in_notation_view = False
    notation_view_start = 0
    notation_view_end = 0
    needs_indent = False
    
    # Find class boundaries
    for i, line in enumerate(lines, 1):
        if line.strip().startswith('class NotationView('):
            notation_view_start = i
            in_notation_view = True
        elif line.strip().startswith('class NotationWidget('):
            notation_view_end = i
            in_notation_view = False
    
    print(f"NotationView: lines {notation_view_start} - {notation_view_end}")
    
    # Fix indentation
    for i, line in enumerate(lines, 1):
        # Start indenting after line 528 within NotationView
        if i > 528 and i < notation_view_end:
            # If line starts with 'def ' at column 0, it needs indentation
            if line.startswith('def ') or line.startswith('# ---'):
                fixed_lines.append('    ' + line)  # Add 4 spaces
                needs_indent = True
            # If we're in a function that needs indent, indent all non-empty lines
            elif needs_indent and line.strip() and not line.startswith('    '):
                # Check if this is a new class or function at top level
                if line.startswith('class '):
                    needs_indent = False
                    fixed_lines.append(line)
                else:
                    # This line is part of the wrongly-indented function
                    # Count existing spaces and add 4
                    stripped = line.lstrip()
                    existing_spaces = len(line) - len(stripped)
                    fixed_lines.append('    ' * (existing_spaces // 4 + 1) + stripped)
            else:
                fixed_lines.append(line)
                if line.strip() and not line.strip().startswith('#') and line[0] != ' ':
                    needs_indent = False
        else:
            fixed_lines.append(line)
            if i >= notation_view_end:
                needs_indent = False
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)
    
    print(f"Fixed {output_file}")

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: fix_indent.py input.py output.py")
        sys.exit(1)
    
    fix_indentation(sys.argv[1], sys.argv[2])
