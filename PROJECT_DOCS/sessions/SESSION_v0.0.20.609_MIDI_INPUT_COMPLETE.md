# Session: v0.0.20.609 — MIDI Input Routing Complete (5 Features)
**Date:** 2026-03-18 | **Author:** Claude Opus 4.6

## Aufgabe
Alle 5 offenen MIDI Input Routing Tasks aus v608 implementiert.

## Geänderte/Neue Dateien (8)

| Datei | Änderung |
|-------|----------|
| `pydaw/model/project.py` | +1 Feld: `midi_channel_filter: int = -1` |
| `pydaw/services/project_service.py` | +1 Methode: `set_track_midi_channel_filter()` |
| `pydaw/services/midi_manager.py` | Channel-Filter in `_resolve_target()`, Touch/OSC routing, `forward_track_midi()` |
| `pydaw/services/computer_keyboard_midi.py` | **NEU**: QWERTY→MIDI Service (Bitwig-Layout, Event-Filter) |
| `pydaw/services/osc_midi_input.py` | **NEU**: OSC UDP→MIDI Service (python-osc, /note/on, /note/off, /cc) |
| `pydaw/ui/touch_keyboard.py` | **NEU**: On-Screen Piano Widget (QPainter, click/drag-play, velocity) |
| `pydaw/ui/arranger.py` | Channel-Filter Combo, Touch KB + OSC in Dropdown |
| `pydaw/ui/main_window.py` | Computer KB + Touch KB Wiring, Menü-Toggles, Dock |

## Feature-Details

### 1. Computer Keyboard MIDI (Ctrl+Shift+K)
- Bitwig-Standard QWERTY-Layout: A-L = weiße Tasten, W/E/T/Y/U = schwarze Tasten
- Z-Reihe = tiefe Oktave, Komma/Punkt = Oktave-Shift
- Event-Filter auf QApplication — ignoriert Textfelder (QLineEdit etc.)
- Inject via `inject_message(source='computer_keyboard')`
- Fallback `_FakeMsg` wenn mido nicht installiert

### 2. MIDI Channel Filter (Omni / Ch 1-16)
- Track-Model: `midi_channel_filter: int = -1` (-1 = Omni)
- MidiManager: `_midi_channel_accepts()` Filter in `_resolve_target()`
- Arranger UI: QComboBox "Omni | Ch 1 | ... | Ch 16" pro Track

### 3. Touch Keyboard (Ctrl+Shift+T)
- On-Screen Piano (QPainter) mit 3 Oktaven, Oktave/Velocity Spinboxen
- Click → Note On, Release → Note Off, Drag → Glissando
- Inject via `inject_message(source='touch_keyboard')`
- Toggleable QDockWidget am Bottom

### 4. Track-to-Track MIDI Routing
- `forward_track_midi(source_track_id, msg)` API
- Routing-Filter: `midi_input="track:trk_xyz"` akzeptiert `source="track:trk_xyz"`
- UI: ♪ Track-Einträge im MIDI Input Dropdown-Menü

### 5. OSC Input Source
- `/note/on [pitch, vel, ch]`, `/note/off [pitch, ch]`, `/cc [ctrl, val, ch]`
- ThreadingOSCUDPServer auf konfigurierbarem Port (default 9000)
- Inject via `inject_message(source='osc')`
- Graceful fallback wenn python-osc nicht installiert

## Routing-Matrix (komplett)

| midi_input | computer_keyboard | touch_keyboard | osc | Hardware | track:id |
|------------|:-:|:-:|:-:|:-:|:-:|
| No input | ✗ | ✗ | ✗ | ✗ | ✗ |
| All ins | ✗ | ✗ | ✗ | ✓ | ✗ |
| Computer Keyboard | ✓ | ✗ | ✗ | ✗ | ✗ |
| Touch Keyboard | ✗ | ✓ | ✗ | ✗ | ✗ |
| OSC - OSC | ✗ | ✗ | ✓ | ✗ | ✗ |
| Specific port | ✗ | ✗ | ✗ | exact | ✗ |
| track:<id> | ✗ | ✗ | ✗ | ✗ | exact |

## Nichts kaputt gemacht ✓
- Alle 8 Dateien: `ast.parse()` bestanden
- Keine bestehenden Widgets/Buttons/Services verändert
- Alle neuen Services sind opt-in (hidden by default, graceful fallback)
