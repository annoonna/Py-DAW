# 📝 SESSION LOG: 2026-02-03 (Duplicate Fix)

**Entwickler:** GPT-5.2
**Zeit:** ~25min
**Task:** Arranger Duplicate Workflow Fix (Ctrl+D / Ctrl+Drag)

## ✅ Ziel
- Ctrl+D soll Clips **nahtlos am Ende** duplizieren (same track)
- Neue Clips dürfen **keine leeren MIDI-Daten** haben
- Ctrl+Drag Duplicate darf **nicht crashen**

## ✅ Änderungen
### 1) Ctrl+D Verhalten korrigiert
- `ProjectService.duplicate_clip()` dupliziert jetzt **horizontal** auf derselben Spur.
- Startposition = `start_beats + length_beats` (End-Snap), mit `round(..., 6)` gegen Float-Drift.
- MIDI-Notes werden via `copy.deepcopy()` übernommen.

### 2) Crash-Fix: add_note Alias
- `ProjectService.add_note()` als Alias für `add_midi_note()` ergänzt.
  (Einige UI-Pfade riefen noch `add_note()` auf.)

### 3) Ctrl+Drag Duplicate: Deepcopy der Notes
- In `ArrangerCanvas.mouseReleaseEvent()` Notes-Kopie jetzt direkt als Deepcopy in `midi_notes[new_id]`.

## 🧪 Manuelle Tests
1) MIDI Clip erstellen → Notes setzen → Clip selektieren → **Ctrl+D**
   - Erwartung: neuer Clip direkt rechts am Ende, mit identischen Notes.
2) Clip ziehen mit **Ctrl gedrückt**
   - Erwartung: Clip bewegt sich, an Originalposition entsteht Copy mit Notes, kein Crash.
3) Audio Clip: Ctrl+D
   - Erwartung: Copy rechts am Ende, gleiche Source.

## Dateien
- `pydaw/services/project_service.py`
- `pydaw/ui/arranger_canvas.py`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`

