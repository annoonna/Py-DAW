# Changelog — v0.0.20.84

## Added
- Hilfe → Arbeitsmappe: Tab „Shortcuts & Befehle“ listet jetzt alle Tastenkombinationen inkl. Erklärung.
  - Auto-Extraktion aus dem Programm: QAction-Shortcuts + QShortcut-Objekte.
  - Ergänzende kuratierte Liste für kontextabhängige Editor-Shortcuts (Arranger / Piano Roll / Notation / Audio / Mixer).

## Changed
- QShortcut-Objekte bekommen Metadaten (Beschreibung), damit sie in der Arbeitsmappe verständlich erscheinen:
  - MainWindow: Ctrl+Tab / Ctrl+Shift+Tab / B
  - Notation-Palette: Alt+1..7 / Alt+. / Alt+R

## Files
- pydaw/ui/workbook_dialog.py
- pydaw/ui/main_window.py
- pydaw/ui/notation/notation_palette.py
