# Session Log — v0.0.20.705

**Datum:** 2026-03-21
**Kollege:** Claude Opus 4.6
**Arbeitspaket:** Plugin Sandbox P2A/P2B/P2C — VST3 Sandbox Worker
**Aufgabe:** VST3 Plugin-Hosting in separatem Subprocess

## Was wurde erledigt

### Phase P2A — VST3 Worker Process ✅
- `plugin_workers/vst3_worker.py`: Standalone Worker mit pedalboard
- Audio-Loop, Parameter-IPC, State Save/Restore, Channel-Detection
- CLI entry point für standalone Nutzung
- SandboxProcessManager routet VST3 zum spezialisierten Worker

### Phase P2B — VST3 GUI in Worker ✅
- ShowEditor/HideEditor IPC-Befehle (Bidirektional)
- Worker-seitig: pedalboard.show_editor()/hide_editor()
- Manager + SandboxedFx: show_editor()/hide_editor() API

### Phase P2C — VST3 Instrument Sandbox ✅
- MIDI IPC: note_on, note_off, all_notes_off, midi_events Batch
- _process_instrument(): MIDI → pedalboard.process(midi_msgs) → Audio
- SandboxedFx: pull() + note_on/off (kompatibel mit Vst3InstrumentEngine)

## Geänderte Dateien
- pydaw/plugin_workers/__init__.py (**NEU**)
- pydaw/plugin_workers/vst3_worker.py (**NEU**)
- pydaw/services/sandbox_process_manager.py (VST3 routing, MIDI/editor relay)
- pydaw/services/sandboxed_fx.py (instrument + editor API)
- pydaw/services/plugin_ipc.py (MIDI + editor IPC)
- VERSION, pydaw/version.py

## Nächste Schritte
1. Phase P3A — VST2 Worker Process (ctypes im Subprocess)
2. Phase P4A — LV2 Worker (lilv im Subprocess)
3. Phase P5A — CLAP Worker (ctypes im Subprocess)

## Offene Fragen an den Auftraggeber
- vst_gui_process.py Legacy-Logik noch nicht migriert (kann parallel bleiben)
- Latenz-Kompensation für Sandbox fehlt (PDC Report via IPC)
