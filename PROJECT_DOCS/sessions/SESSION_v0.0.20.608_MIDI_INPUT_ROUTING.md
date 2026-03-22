# Session: v0.0.20.608 — Bitwig-Style MIDI Input Routing
**Date:** 2026-03-18 | **Author:** Claude Opus 4.6

## Aufgabe
MIDI Input Routing pro Track — exakt wie Bitwig Studio, mit kategorisiertem Dropdown-Menü.

## Geänderte Dateien (5)

| Datei | Änderung |
|-------|----------|
| `pydaw/model/project.py` | +1 Feld: `midi_input: str = ""` auf Track-Klasse |
| `pydaw/services/project_service.py` | +2 Methoden: `set_track_midi_input()`, `get_track_effective_midi_input()` |
| `pydaw/services/midi_manager.py` | Queue-Items als `(source_port, msg)` Tuples, `_midi_input_accepts()` Filter, `inject_message()` API |
| `pydaw/ui/arranger.py` | MIDI Input Dropdown + Output Label in Track-Row, `_build_midi_input_menu()` mit Bitwig-Style Kategorien |
| `pydaw/ui/main_window.py` | Wiring: `arranger.set_midi_manager(services.midi)` |

## Architektur-Entscheidungen

### 1. Track Model: `midi_input: str = ""`
- Leerer String = Auto-Detect (Instrument → "All ins", Audio/FX/Master → "No input")
- Backwards-kompatibel: Alle bestehenden Tracks ohne das Feld bekommen automatisch den richtigen Default
- Werte: "No input" | "All ins" | "Computer Keyboard" | exakter Port-Name | "track:<track_id>"

### 2. MidiManager: Source-Port Tagging
- Queue-Items sind jetzt `(source_port, msg)` Tuples statt nur `msg`
- `_run_reader()` taggt mit dem Port-Namen
- `_drain_queue()` entpackt sicher (Backwards-Compat für alte Tuple-lose Items)
- `_midi_input_accepts(track, source_port)` → True/False nach Bitwig-Regeln

### 3. Routing-Regeln (Bitwig-konform)
- "No input" → kein MIDI
- "All ins" → alle Hardware-Ports (NICHT Computer Keyboard — wie in Bitwig!)
- "Computer Keyboard" → nur `source="computer_keyboard"`
- Spezifischer Port → nur dieser Port
- "track:<id>" → internes Track-to-Track MIDI Routing (vorbereitet)

### 4. UI: Kategorisiertes Dropdown-Menü
- **NOTE INPUTS**: No input, All ins, Computer Keyboard, + verbundene Controller mit 🎹
- **Add MIDI Controller**: Submenu mit nicht-verbundenen Ports
- **TRACKS**: Alle anderen Tracks für MIDI-Through-Routing

### 5. inject_message() API
- Für Computer Keyboard, OSC, und Track-Routing
- Ermöglicht UI-Events als MIDI in die Pipeline einzuspeisen
- Source-Tag wird für Input-Routing-Filter verwendet

## Nichts kaputt gemacht ✓
- Alle bestehenden Tracks ohne `midi_input` Feld bekommen Auto-Default
- Queue-Drain hat Backwards-Compat für nicht-Tuple Items
- Alle 5 Dateien syntaktisch verifiziert (ast.parse)
- Keine bestehenden Buttons/Slider/Widgets verändert
- Record Arm Logik unverändert (nur um Input-Filter erweitert)

## Nächste Schritte für den nächsten Kollegen
1. **Computer Keyboard MIDI**: QWERTY keyPress → `inject_message()` aufrufen (Piano-Roll hat evtl. schon Key-Handling)
2. **OSC Input**: OSC-Server → `inject_message(source='osc')` 
3. **Track-to-Track MIDI**: Wenn Track A `midi_input="track:trk_xyz"` hat, muss Engine die MIDI-Events von Track xyz weiterleiten
4. **Touch Keyboard**: On-Screen Keyboard Widget → `inject_message(source='touch_keyboard')`
5. **MIDI Channel Filter**: Pro Track optional nur bestimmte MIDI-Kanäle (wie Bitwig "Channel" Dropdown neben Input)
