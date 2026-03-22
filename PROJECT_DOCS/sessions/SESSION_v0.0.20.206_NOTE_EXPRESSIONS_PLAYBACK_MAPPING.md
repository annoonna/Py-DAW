# SESSION v0.0.20.206 — Note Expressions Playback Mapping (Velocity/Chance + CC74/Pressure)

**Date:** 2026-03-03  
**Assignee:** GPT-5.2 Thinking (ChatGPT)  
**Directive:** Nichts kaputt machen (safe, opt-in, backward compatible)

## Kontext
User-Report: "Einstellungen wirken sich nicht auf den Sound aus" bei Note Expressions.

Root cause:
- Render Cache Keys/Hashes haben Expressions ignoriert.
- In Teilen wurde sogar falsch gehasht (`start`/`length` statt `start_beats`/`length_beats`), wodurch Änderungen nicht invalidiert wurden.

## Ziel
- Note Expressions sollen **hörbar** werden (mindestens am Note-On):
  - Velocity (t=0.0)
  - Chance (t=0.0, deterministisch)
  - Timbre → CC74 (t=0.0, optional)
  - Pressure → Poly Aftertouch (polytouch) (t=0.0, optional)

Micropitch/MPE bewusst NICHT in dieser Runde.

## Änderungen (safe)
### 1) Neues Playback‑Eval Modul
**Neu:** `pydaw/audio/note_expression_eval.py`
- `effective_velocity()`
- `effective_chance()`
- `should_play_note()` (deterministisch)
- `cc74_value()` / `pressure_value()`

### 2) SF2 Render: MIDI Events + Hash Fix
**File:** `pydaw/audio/midi_render.py`
- Content hash nutzt nun korrekt `start_beats/length_beats` und inkludiert Expressions JSON.
- Beim MIDI‑File Build:
  - Chance gate → skip note
  - Velocity expr → note_on velocity
  - Timbre expr → CC74
  - Pressure expr → polytouch
- Reihenfolge bei gleicher Zeit: note_off → cc/aftertouch → note_on
- Optional advanced QSettings toggles (Defaults True):
  - `audio/note_expr_apply_velocity`
  - `audio/note_expr_apply_chance`
  - `audio/note_expr_send_cc74`
  - `audio/note_expr_send_pressure`

### 3) Arranger Hash / Tie-Coerce preserves expressions
**File:** `pydaw/audio/arrangement_renderer.py`
- `_midi_notes_content_hash` inkludiert Expressions.
- `_NoteObj` enthält jetzt `expressions` + `expression_curve_types`, damit `_apply_ties_to_notes()` nichts verliert.

### 4) Live‑MIDI Fallback: Chance/Velocity
**File:** `pydaw/audio/audio_engine.py`
- PreparedMidiEvent Scheduling berücksichtigt Velocity/Chance (t=0.0)

## Dokumentation
- `PROJECT_DOCS/plans/NOTE_EXPRESSIONS.md` erweitert um „Playback Mapping“

## Version
- Bump: `0.0.20.205` → `0.0.20.206`
- Updated:
  - `VERSION`
  - `pydaw/version.py`
  - `pydaw/model/project.py` default version

## Testplan (manuell)
1) SF2 Track: Note mit Velocity Expr (Lane) → Render muss hörbar lauter/leiser werden.
2) Chance Expr (z.B. 0.25) → deterministisches Pattern (gleich bei Reopen/Rerender).
3) Timbre/Pressure (wenn SF2 reagiert) → Klang ändert sich zumindest bei Instruments die CC74/Aftertouch nutzen.
4) Sampler/Drum Track (non-sf2): Chance/Velocity sollten beim Playback wirken.

## Nächste AVAILABLE Ideen
- UI‑Toggles für Playback Mapping (statt QSettings only)
- Micropitch/MPE Playback Mode (separat, risk‑controlled)
- Per‑note continuous CC curves (mid‑note updates) (perf‑safe batch)
