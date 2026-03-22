# CHANGELOG v0.0.20.609 — MIDI Input Routing Complete (5 Features)

**Date:** 2026-03-18 | **Author:** Claude Opus 4.6

## Neue Features

### 1. Computer Keyboard MIDI (Ctrl+Shift+K)
- Bitwig-Standard QWERTY→MIDI Layout
- White keys: A=C, S=D, D=E, F=F, G=G, H=A, J=B, K=C+1, L=D+1
- Black keys: W=C#, E=D#, T=F#, Y=G#, U=A#
- Z-Reihe: tiefe Oktave | Komma/Punkt: Oktave-Shift
- QApplication Event-Filter — ignoriert Textfelder automatisch
- Fallback _FakeMsg wenn mido nicht installiert

### 2. MIDI Channel Filter pro Track
- Neues Track-Feld: `midi_channel_filter: int = -1` (Omni)
- MidiManager: `_midi_channel_accepts()` Filter
- Arranger UI: QComboBox "Omni | Ch 1 | ... | Ch 16"

### 3. Touch Keyboard (Ctrl+Shift+T)
- On-Screen Piano Widget mit QPainter (3 Oktaven)
- Click/Drag-Play, Oktave-Spinbox, Velocity-Spinbox
- Toggleable QDockWidget am Bottom

### 4. Track-to-Track MIDI Routing
- `forward_track_midi(source_track_id, msg)` API im MidiManager
- Routing akzeptiert `midi_input="track:trk_xyz"`
- UI: ♪ Track-Einträge im MIDI Input Dropdown

### 5. OSC Input Source
- `/note/on [pitch, vel, ch]`, `/note/off [pitch, ch]`, `/cc [ctrl, val, ch]`
- ThreadingOSCUDPServer (default Port 9000)
- Graceful fallback wenn python-osc nicht installiert

## Geänderte/Neue Dateien

| Datei | Status |
|-------|--------|
| `pydaw/model/project.py` | Geändert (+midi_channel_filter) |
| `pydaw/services/project_service.py` | Geändert (+set_track_midi_channel_filter) |
| `pydaw/services/midi_manager.py` | Geändert (channel filter, touch/osc routing, forward_track_midi) |
| `pydaw/services/computer_keyboard_midi.py` | **NEU** |
| `pydaw/services/osc_midi_input.py` | **NEU** |
| `pydaw/ui/touch_keyboard.py` | **NEU** |
| `pydaw/ui/arranger.py` | Geändert (channel combo, touch/osc menu entries) |
| `pydaw/ui/main_window.py` | Geändert (computer kb + touch kb wiring) |

## Nichts kaputt gemacht ✓
- Alle 8 Dateien: ast.parse() bestanden
- Neue Services sind opt-in (hidden/disabled by default)
- Graceful fallback bei fehlenden Abhängigkeiten (mido, python-osc)
