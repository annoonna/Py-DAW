# Session v0.0.20.231 — LV2: lv2info Parser Fix (stderr-safe + whitespace Port split) + install.py PEP668 venv bootstrap

**Date:** 2026-03-04  
**Assignee:** GPT-5.2 Thinking (ChatGPT)  
**Directive:** SAFE — minimal, targeted changes only

## Problem (User Report)
- LV2 Device zeigt weiterhin: **"Keine LV2 Controls gefunden"**
- `lv2info <URI>` zeigt aber ControlPorts.
- Zusätzlich: `install.py` / `pip install` schlagen auf Kali mit **externally-managed-environment (PEP 668)** fehl, wenn versehentlich System-Python genutzt wird.

## Root Cause
1) `lv2info` schreibt Warnungen/Fehler über kaputte LV2 Bundles nach **stderr** (z.B. missing manifest.ttl).
   Unsere Parser-Implementierung hat stdout+stderr zusammengefügt → die Fehlerzeilen standen vor den Port-Blöcken und verhinderten das Split/Match.
2) Port-Blöcke werden bei `lv2info` oft **eingrückt** ausgegeben (`\tPort 0:`). Unser Split war zu strikt (nur `\nPort ...` ohne Whitespace).

## Fix (safe)
### LV2 Param-UI Fallback (`lv2info`)
- Parser nutzt **stdout-only** (stderr wird ignoriert), mit fallback auf stderr nur wenn stdout leer ist.
- Port-Split und Port-Erkennung erlauben **Whitespace vor "Port N:"**.

### Installer Hardening (Kali/Debian PEP668)
- `install.py` erstellt/verwendet automatisch ein lokales `./myenv` venv und nutzt dessen Python für pip,
  um System-Python + PEP668 Fehler zu vermeiden (SAFE: keine Systemänderung).

## Files changed
- `pydaw/audio/lv2_host.py`
- `install.py`
- `VERSION`, `pydaw/version.py`, `pydaw/model/project.py`
- `PROJECT_DOCS/sessions/LATEST.md`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`

## Test
- `lv2info http://eq10q.sourceforge.net/bassup` liefert ControlPorts → UI erzeugt Slider/Controls.
- `python3 install.py` auf Kali ohne aktiviertes venv → erstellt `./myenv` und installiert requirements ohne PEP668.

