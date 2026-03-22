# CHANGELOG v0.0.20.608 — Bitwig-Style MIDI Input Routing

**Date:** 2026-03-18 | **Author:** Claude Opus 4.6

## Neue Features

### MIDI Input Routing pro Track (Bitwig Studio Parity)
- **Track Model**: Neues Feld `midi_input: str` mit intelligentem Auto-Default
  - Instrument-Tracks → "All ins" (empfängt alle Hardware-Controller)
  - Audio/FX/Master-Tracks → "No input" (kein MIDI)
  - Backwards-kompatibel: Bestehende Projekte brauchen keine Migration
- **MidiManager Routing-Engine**: Source-Port Tagging auf Queue-Ebene
  - Jede MIDI-Nachricht wird mit ihrem Quell-Port getaggt
  - `_midi_input_accepts()` filtert pro Track nach Bitwig-Regeln
  - "All ins" akzeptiert Hardware-Ports, nicht Computer Keyboard (wie Bitwig!)
- **Arranger UI**: Kategorisiertes Dropdown-Menü pro Track-Row
  - **NOTE INPUTS**: No input, All ins, Computer Keyboard
  - **🎹 Connected Controllers**: Dynamisch aus MidiManager
  - **Add MIDI Controller**: Submenu mit verfügbaren aber nicht verbundenen Ports
  - **♪ TRACKS**: MIDI von anderen Tracks routen (Inter-Track MIDI)
- **Output Label**: "→ Master" / "→ Group" Anzeige pro Track
- **inject_message() API**: Für virtuelle MIDI-Quellen (Computer Keyboard, OSC, Track-Routing)

## Geänderte Dateien

| Datei | Zeilen +/- |
|-------|-----------|
| `pydaw/model/project.py` | +5 |
| `pydaw/services/project_service.py` | +24 |
| `pydaw/services/midi_manager.py` | +62 |
| `pydaw/ui/arranger.py` | +182 |
| `pydaw/ui/main_window.py` | +4 |

## Nichts kaputt gemacht ✓
- Alle 5 Dateien: `ast.parse()` bestanden
- Bestehende Track-Logik unverändert
- Record Arm Verhalten identisch (nur um Input-Filter erweitert)
- Queue-Drain hat Backwards-Compat für alte Nachrichtenformat
