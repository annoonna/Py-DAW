# SESSION v0.0.20.210 — 2026-03-04

## Kontext
User-Report (Pro Drum Machine):
- Nach „Reverse“ spielt das Sample nicht bis hinten (wirkt abgeschnitten).
- Wunsch: pro Slot Start/End (wo beginnt/endet das Sample) und pro Slot mehrere FX-Devices.

Direktive: **nichts kaputt machen**.

## Root Cause
- DrumMachine triggert One‑Shots mit `duration_ms=140/160` → ProSamplerEngine stoppt Preview per `_preview_remaining` unabhängig von Sample-Länge.

## Änderungen (safe)
### 1) Full One‑Shot Playback
- `DrumMachineEngine.trigger_note()` default `duration_ms=None`.
- `DrumMachineEngine.note_on()` nutzt `duration_ms=None`.
- `DrumMachineWidget._preview_slot()` nutzt `duration_ms=None`.

### 2) Region Start/End
- `ProSamplerEngine.EngineState`: neues Feld `end_position`.
- `set_region_norm(start,end)` + Clamp-Regeln.
- `pull()` nutzt `end_position` als End-Marker bei nicht-loopendem Playback.
- UI: Start/End‑Knobs im DrumMachine Slot‑Editor + Marker im Waveform.

### 3) Per‑Slot FX Rack
- Dialog `SlotFxRackDialog`: EQ5 (optional), Distortion, Delay (Mix/Time/FB), Reverb, Chorus.
- Umsetzung nutzt nur vorhandene Sampler‑FX + neue optionale EQ5‑Stufe (disabled by default).

## Dateien
- `pydaw/plugins/drum_machine/drum_widget.py`
- `pydaw/plugins/drum_machine/drum_engine.py`
- `pydaw/plugins/sampler/sampler_engine.py`
- `pydaw/plugins/sampler/dsp.py`
- `pydaw/plugins/sampler/ui_widgets.py`
- `pydaw/version.py`
- `VERSION`
