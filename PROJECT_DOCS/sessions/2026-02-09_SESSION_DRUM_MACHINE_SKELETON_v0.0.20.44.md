# SESSION — Pro Drum Machine Skeleton (v0.0.20.44)
**Datum:** 2026-02-09  
**Kollege:** GPT-5.2 Thinking  
**Ziel:** Drum-Modul als Plugin (Device Panel) hinzufügen, ohne Core zu verändern.

## Kontext
User will ein Ableton/Pro-DAW-inspiriertes Drum-Modul dort, wo derzeit der Sampler als Device sitzt.
Wichtig war: zuerst ein **testbares Skeleton** (UI + Grundverdrahtung), danach Ausbau.

## ✅ Umgesetzt (Phase 1 / Skeleton)
- Neues Instrument-Plugin **Pro Drum Machine** (Device): 4x4 Pads (16 Slots)
- Pro Slot **eigene** `ProSamplerEngine` (keine globalen Parameter)
- Pads akzeptieren Drag&Drop von Audio-Files (wav/flac/ogg/mp3/aif)
- Pull-Source Summing: DrumMachineEngine mischt alle Slots und gibt Stereo-Buffer zurück
- `_pydaw_track_id` wird am Pull-Fn gesetzt → Track-Fader + VU Meter greifen sofort
- MIDI Mapping: **C1 (36) = Slot1**, chromatisch nach oben
- Slot-Editor (Skeleton): Waveform-Preview + Gain/Pan/Tune + Filter (off/LP/HP/BP)
- Pattern Generator (Placeholder): Style/Intensity/Bars → schreibt Notes in **aktiven** MIDI-Clip

## Dateien
**NEU:**
- `pydaw/plugins/drum_machine/__init__.py`
- `pydaw/plugins/drum_machine/drum_engine.py`
- `pydaw/plugins/drum_machine/drum_widget.py`

**UPDATE:**
- `pydaw/plugins/registry.py` (Instrument-Liste)
- `VERSION`, `pydaw/version.py`
- `PROJECT_DOCS/progress/TODO.md`
- `PROJECT_DOCS/progress/DONE.md`

## Wie testen
1. DAW starten
2. Track auswählen → rechts im Browser `Instruments`
3. **Pro Drum Machine** doppelklicken oder "Add to Device"
4. Audio-Files aus Browser/Samples auf Pads droppen
5. Pad klicken/halten → Preview sollte spielen + VU Meter bewegen
6. MIDI-Clip auswählen → Generate → Pattern sollte sichtbar sein (C1..)

## Nächste Steps (Phase 2 Wiring)
- Persistenz: Slot-Sample-Paths + Parameter in Project speichern/restore
- Polyphony/Performance: Slot-Engine ohne Python-Loops (numpy/numba/C-backend)
- Voller Waveform-Editor: Start/End/Loop/Fade Markers je Slot
- Pattern Generator "Style-Mixer" (multi-style blend) + humanize + swing
- Clip-Erzeugung falls kein aktiver MIDI-Clip vorhanden (Auto-create @ Playhead)
