# v0.0.20.213 — Safe Rollback auf 210 + Tune ±24 + Qt-Hardening Log-Fix

**Datum:** 2026-03-04  
**Assignee:** GPT-5.2 Thinking (ChatGPT)  
**Directive:** Nichts kaputt machen (Core unverändert)

## Kontext
In v0.0.20.211/212 sind Instrumente zeitweise nicht mehr sauber nutzbar bzw. UI/Widgets wirken „kaputt“.
Der bereitgestellte Backup-Stand v0.0.20.210 ist stabiler und lädt die Instrumente ohne den PyQt6-QPointF Import-Fehler.

## Änderungen (minimal & sicher)
1) **Pro Drum Machine – Tune Mapping**
- Tune bleibt 0..100.
- Intern jetzt **±24 Semitones** statt ±12 (betrifft UI-Änderung + Automation-Apply).
- Datei: `pydaw/plugins/drum_machine/drum_widget.py`

2) **Qt Hardening – disconnect() Log-Spam reduziert**
- `TypeError: 'method' object is not connected` wird nun still ignoriert (harmlos).
- Andere Exceptions werden weiterhin geloggt.
- Datei: `pydaw/ui/qt_hardening.py`

3) **Version bump**
- `VERSION`, `pydaw/version.py` → 0.0.20.213

## Nicht geändert (bewusst)
- Kein Umbau am Audio-Core / Engine.
- Keine neuen UI-Features/Refactors übernommen, um Stabilität zu garantieren.

## Test
- Start: `gdb -batch -ex "run" -ex "bt" --args python3 main.py`
- Pro Drum Machine: Tune auf 0/50/100 prüfen → deutlich hörbar (±24).
- Signal-Disconnect Logs sollten nicht mehr in ERROR-Spam ausarten.

