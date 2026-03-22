# Session Log — v0.0.20.99

**Datum:** 2026-02-21
**Bearbeiter:** Claude Opus 4.6 (Anthropic)

## Bugs gefixt

### 1. Rechtsklick-Kontextmenü blockiert (KRITISCH)

**Problem:** Jeder Rechtsklick im Arranger startete sofort eine Lasso-Selection
und setzte `_suppress_next_context_menu = True`. Dadurch wurde das Kontextmenü
mit "Duplizieren", "Löschen" etc. nie angezeigt.

**Ursache:** `mousePressEvent` fing alle `RightButton`-Events ab und startete
Lasso-Selection bevor `contextMenuEvent` feuern konnte.

**Fix:** Rechtsklick-Lasso komplett entfernt. Rechtsklick im Arranger geht
jetzt direkt an `contextMenuEvent` (Clip-Menü, Track-Menü etc.).
Lasso-Selection funktioniert weiterhin per Linksklick auf leere Fläche.
Nur Rechtsklick im Ruler (Loop zeichnen) wird noch abgefangen.

### 2. Leertaste (Space) für Play/Pause fehlte

**Problem:** Kein Spacebar-Shortcut existierte. Leertaste tat nichts.

**Fix:** 
- Globaler `QShortcut("Space")` in `main_window.py` → `_on_play_clicked()`
- Zusätzlich `Key_Space` in `arranger_canvas.py` `keyPressEvent` → `transport.toggle_play()`

### 3. Ctrl+Drag Kopie an falscher Position

**Problem:** Beim Ctrl+Drag wurde das Original verschoben und die Kopie
an der alten Position erstellt. Erwartet: Original bleibt, Kopie am Drop-Ziel.

**Fix:** 
- Original-Position wird beim Drag-Start gespeichert (`_drag_copy_original_start/track`)
- Bei Release: Original wird zurück an Ursprungsposition verschoben
- Kopie wird an der Drop-Position erstellt (wie in jeder DAW)

### Geänderte Dateien:
- `pydaw/ui/arranger_canvas.py` (Alle 3 Fixes)
- `pydaw/ui/main_window.py` (Space-Shortcut)
- `pydaw/version.py` (0.0.20.98 → 0.0.20.99)
