# SESSION LOG: 2026-03-16 — v0.0.20.517

**Entwickler:** Claude Opus 4.6
**Zeit:** 2026-03-16
**Task:** Ctrl+Drag Copy, Auto Track-Type, Belegte Audio-Spuren Morph

## 3 FEATURES IN EINEM RUTSCH

### 1. Ctrl+Drag = Copy statt Move
- Ctrl gehalten beim Cross-Track-Drag → Device wird KOPIERT (bleibt auf Quellspur)
- Ohne Ctrl → Device wird VERSCHOBEN (wie bisher in v516)
- `_is_ctrl_held()` prueft `QApplication.keyboardModifiers()`
- Gilt fuer Instrumente, Audio-FX UND Note-FX

### 2. Automatische Track-Typ-Anpassung
- Wenn ein Instrument per Move von einer Instrument-Spur entfernt wird
- UND die Quellspur danach kein plugin_type mehr hat
- → track.kind wird automatisch auf "audio" zurueckgesetzt
- Sicher: nur bei plugin_type=="" und kind=="instrument"

### 3. Belegte Audio-Spuren Morph
- Audio-Spuren mit Clips UND/ODER FX → can_apply=True
- apply_mode="audio_to_instrument_with_content"
- requires_confirmation=True → Bestaetigungsdialog wird gezeigt
- Audio-Clips und FX-Kette bleiben KOMPLETT erhalten
- Nur track.kind wird geaendert (Bitwig-Style Hybrid-Konvertierung)
- Undo per Ctrl+Z stellt alles komplett wieder her

## TESTERGEBNISSE
1. Leere Audio-Spur → can_apply=True, mode=minimal_empty_audio, confirm=False ✅
2. Audio+Clips → can_apply=True, mode=audio_to_instrument_with_content, confirm=True ✅
3. Audio+FX → can_apply=True, mode=audio_to_instrument_with_content, confirm=True ✅
4. Instrument-Spur → can_apply=False, mode=blocked ✅
5. Apply auf belegter Spur → ok=True, FX erhalten, Clips erhalten ✅
6. Undo → kind zurueck auf audio ✅

## GEAENDERTE DATEIEN
- `pydaw/ui/main_window.py` (~40 Zeilen)
- `pydaw/services/smartdrop_morph_guard.py` (~20 Zeilen)

## NICHTS KAPUTT GEMACHT
- Alle bestehenden Pfade unveraendert
- Browser-Drops unveraendert
- Internes Device-Reorder unveraendert
