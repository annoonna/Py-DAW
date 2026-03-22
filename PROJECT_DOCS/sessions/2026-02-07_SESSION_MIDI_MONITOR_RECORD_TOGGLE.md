# 📌 Session Log — 2026-02-07 — MIDI Monitoring vs Recording Toggle (v0.0.20.3)

## Ziel
- Live-MIDI (Keyboard) soll **hörbar** sein, ohne dass sofort Noten in den Clip geschrieben werden.
- Noten sollen **nur** in den aktiven MIDI-Clip geschrieben werden, wenn **MIDI-Record** aktiv ist.

## Änderungen
- `pydaw/services/midi_manager.py`
  - `set_record_enabled(bool)` + `is_record_enabled()` ergänzt
  - Default: `MIDI Record = OFF`
  - Note-Commit (add_midi_note) wird **nur** ausgeführt, wenn MIDI-Record aktiv ist
- `pydaw/ui/pianoroll_editor.py`
  - Signal `record_toggled(bool)` ergänzt
  - PianoRoll-Button **Record** steuert nun MIDI-Record
- `pydaw/ui/main_window.py`
  - `editor_tabs.pianoroll.record_toggled -> services.midi.set_record_enabled` verdrahtet
- Version bump: `pydaw/version.py` → `0.0.20.3`

## Ergebnis / Erwartetes Verhalten
- Spur **armed (R)** + MIDI Input verbunden → **Monitoring/Thru** funktioniert (Sampler hört)
- PianoRoll **Record** OFF → keine MIDI-Noten werden geschrieben
- PianoRoll **Record** ON → Noten werden beim Spielen in den aktiven Clip geschrieben

## Nächste Schritte (optional)
- Eigener Track-Header-Button „Monitor/IN“ (Speaker-Icon) + persistente Einstellung pro Track
- Monitoring auch ohne aktiven Clip (nur Spur selektiert)
