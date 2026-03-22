# SESSION v0.0.20.71 — 2026-02-14

## Task
**Help → Arbeitsmappe** im Programm fertigstellen (Team-Dokumente direkt in der GUI).

## Problem / Motivation
- Kollegen sollen ohne Terminal-Suche sofort sehen:
  - README_TEAM
  - MASTER_PLAN / VISION
  - TODO / DONE
  - Letzter Stand (LATEST + letzte Session)
- Struktur ist historisch inkonsistent (Sessions teils in `PROJECT_DOCS/sessions`, teils in `PROJECT_DOCS/progress/sessions`).
  → Arbeitsmappe muss **beide** unterstützen.

## Umsetzung
- `WorkbookDialog` überarbeitet/gehärtet:
  - Projekt-Root + `PROJECT_DOCS/` werden automatisch gefunden (CWD + Parents + Fallback über `__file__`).
  - Tabs:
    - Start (zeigt progress/LATEST + letzte Session)
    - README_TEAM
    - MASTER_PLAN, VISION
    - TODO, DONE
    - Progress: LATEST
    - Letzte Session (unterstützt `sessions/LATEST.md` Pointer + Fallback nach mtime)
    - Nächste Schritte (extrahiert AVAILABLE Tasks aus TODO)
    - Shortcuts & Befehle (embedded Cheat-Sheet)
  - Buttons:
    - **Ordner öffnen** (PROJECT_DOCS)
    - **Datei öffnen** (je Tab, wenn eine Datei existiert)
    - **↻ Aktualisieren** (re-scan Root/Docs + refresh)
  - Defensive Reads: fehlende Dateien/Ordner dürfen nicht crashen.

## Geänderte Dateien
- `pydaw/ui/workbook_dialog.py`
- `VERSION`, `pydaw/version.py`, `pydaw/model/project.py`
- `PROJECT_DOCS/progress/LATEST.md`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`

## Testplan
1) App starten im Projektordner.
2) Menü → **Hilfe → Arbeitsmappe** (oder **F1**)
3) Erwartung:
   - Dialog öffnet ohne Crash.
   - Start-Tab zeigt `progress/LATEST` + letzte Session.
   - "Ordner öffnen" öffnet PROJECT_DOCS.
   - "Datei öffnen" öffnet z.B. TODO.md im System-Editor.
4) App starten *außerhalb* des Projektordners → Arbeitsmappe zeigt Hinweis "nicht gefunden", kein Crash.

