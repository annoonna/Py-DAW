# SESSION v0.0.20.187 (2026-03-01)

## Ziel
Regressionen beseitigen ("nichts kaputt machen") und Verhalten wie in v0.0.20.176 wiederherstellen, während UI-Additions (Track ▾, Favorites/Recents) erhalten bleiben.

## Änderungen
- Fix: QAction/QPushButton Signal-Signaturen: `lambda _=False:`
- Fix: `ProjectService.get_clip()` (UI-Kompat)
- Fix: AudioEventEditor robustes Clip-Lookup
- Fix: `qt_hardening` Slot-Wrap: dedupe + extra-args tolerance

## Ergebnis
Start stabil, keine Log-Flut, Aktionen/Buttons wieder funktionsgleich zu v0.0.20.176.
