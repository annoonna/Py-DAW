# Session v0.0.20.203 — PianoRoll: Grid-Cache Hotfix (Safe)

Datum: 2026-03-03
Kollege: GPT-5.2

## Kontext
User-Feedback nach v0.0.20.202: "du hast das ganze grid gelöscht".

In v0.0.20.202 wurde ein Background/Grid-Cache eingeführt. Dabei entstand ein Bug:
- Die Cache-Funktion rief sich selbst rekursiv auf (statt eine "uncached" Routine aufzurufen).
- Zusätzlich wurden im selben Block Variablen genutzt, die im Fehlerfall nicht gesetzt waren.
- Ergebnis: Grid/Background konnte komplett ausfallen → Piano-Roll wirkt leer.

## Ziel
- Grid wieder zuverlässig sichtbar machen.
- Performance-Verbesserung behalten (Cache), aber **ohne** Funktions-Regression.
- Oberste Direktive: **nichts kaputt machen**.

## Änderungen
### 1) Paint-Pipeline repariert
- `paintEvent()` ist wieder der einzige Entry-Point fürs Zeichnen.
- Background/Grid wird als **statischer Layer** in ein QPixmap gecached.
- Notes, Ghost Notes, Playline, Selection, Expressions bleiben **dynamisch**.

### 2) Cache-Invalidation
Der Cache wird jetzt invalidiert bei:
- `_update_canvas_size()` (Resize/Geometry)
- `set_grid_mode()`
- `set_grid_beats()`

### 3) Fallback-Sicherheit
Falls Cache-Build fehlschlägt:
- Grid/Background wird **direkt** gezeichnet (niemals "leeres" Grid).

## Betroffene Dateien
- `pydaw/ui/pianoroll_canvas.py`

## Ergebnis
- Grid ist wieder sichtbar.
- Interaktion bleibt flüssig (Background/Grid Cache).
- Keine Änderungen an Note-Editing Logik, Clip-Handling oder Engine.

