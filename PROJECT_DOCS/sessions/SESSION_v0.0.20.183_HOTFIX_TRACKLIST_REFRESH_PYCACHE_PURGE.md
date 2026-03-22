# Session: v0.0.20.184 — Hotfix: TrackList.refresh Start-Crash + Pycache-Purge

**Datum:** 2026-03-01  
**Assignee:** GPT-5.2 Thinking (ChatGPT)  
**Direktive:** Nichts kaputt machen (nur safe/additiv)

## Ausgangslage
Beim Start (MainWindow → ArrangerView → TrackList) tritt auf:

```
AttributeError: 'TrackList' object has no attribute 'refresh'
```

## Ursache
In der Praxis wird häufig eine neue TEAM_READY ZIP über einen existierenden Ordner entpackt.
Python kann dann alte `__pycache__/*.pyc` laden, wenn Zeitstempel/Hash weiterhin passen.
Das erzeugt "ghost" Bugs, die nicht mit den sichtbaren `.py` Dateien übereinstimmen.

## Umsetzung
### 1) TrackList Refresh robust
- `TrackList.__init__` nutzt jetzt `_refresh_impl()`.
- `refresh()` bleibt erhalten und ruft intern `_refresh_impl()` auf (Compatibility).

### 2) Pycache purge (lokal)
- `main.py` entfernt beim Start rekursiv lokale `__pycache__` Ordner und `*.pyc` Dateien im Projektordner.
- Optional deaktivierbar: `PYDAW_PURGE_PYCACHE=0`.
- Zusätzlich: `sys.dont_write_bytecode=True`.

## Dateien geändert
- `main.py`
- `pydaw/ui/arranger.py`
- `VERSION`
- `pydaw/version.py`
- `PROJECT_DOCS/progress/LATEST.md`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`
- `PROJECT_DOCS/sessions/LATEST.md`

## Testplan
1) Start:
   - `gdb -batch -ex "run" -ex "bt" --args python3 main.py`
2) Erwartung:
   - Keine Start-Tracebacks.
   - Arranger + TrackList sichtbar.
