# CHANGELOG v0.0.20.705 — VST3 Sandbox Worker (P2A/P2B/P2C)

**Datum:** 2026-03-21
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Plugin Sandbox Roadmap, Phase P2A/P2B/P2C

## Was wurde gemacht

### P2A — VST3 Worker Process
- `pydaw/plugin_workers/vst3_worker.py` (**NEU**): Standalone VST3 Worker
  - Lädt Plugin via pedalboard im Subprocess
  - Audio-Loop: SharedAudioBuffer → plugin.process() → Output
  - Parameter-Updates via IPC (set_param → raw_value)
  - State Save/Restore: raw_state ↔ Base64
  - Channel-Detection, Error-Handling, Bypass-Mode
  - CLI: `python3 -m pydaw.plugin_workers.vst3_worker --path ... --socket ...`
- SandboxProcessManager routet VST3 automatisch zum vst3_worker

### P2B — VST3 GUI in Worker
- ShowEditor/HideEditor IPC-Befehle in PluginIPCClient
- Worker ruft pedalboard.show_editor()/hide_editor() auf
- SandboxProcessManager.show_editor()/hide_editor() Relay
- SandboxedFx.show_editor()/hide_editor() API

### P2C — VST3 Instrument Sandbox
- MIDI IPC: note_on, note_off, all_notes_off, midi_events (Batch)
- PluginIPCClient: send_note_on/off/all_notes_off/midi_events
- SandboxProcessManager: MIDI Relay (6 neue Methoden)
- SandboxedFx: note_on/note_off/all_notes_off/pull (Instrument-API)
- Worker: _process_instrument() — MIDI → plugin.process(midi_msgs) → Audio
- Worker: pending_midi Buffer, instrument mode detection

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/plugin_workers/__init__.py | **NEU**: Package init |
| pydaw/plugin_workers/vst3_worker.py | **NEU**: VST3 Worker (FX + Instrument) |
| pydaw/services/sandbox_process_manager.py | VST3 routing, MIDI relay, editor relay |
| pydaw/services/sandboxed_fx.py | note_on/off, pull, show/hide_editor |
| pydaw/services/plugin_ipc.py | MIDI + editor IPC methods |
| VERSION | 0.0.20.705 |
| pydaw/version.py | 0.0.20.705 |

## Was als nächstes zu tun ist
- Phase P3A — VST2 Worker Process (ctypes im Subprocess)
- Phase P4A — LV2 Worker (lilv im Subprocess)
- Phase P5A — CLAP Worker (ctypes im Subprocess)
- Offen: vst_gui_process.py Logik in Worker integrieren
- Offen: Plugin-Latency Report via IPC (PDC)

## Bekannte Probleme / Offene Fragen
- vst_gui_process.py Legacy-Code noch nicht in Worker migriert
- Latenz-Kompensation für Sandbox noch nicht implementiert
- Praxistest mit echtem VST3-Plugin steht aus (braucht pedalboard + Plugin)
