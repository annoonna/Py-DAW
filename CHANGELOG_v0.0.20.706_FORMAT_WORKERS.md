# CHANGELOG v0.0.20.706 — VST2/LV2/LADSPA/CLAP Sandbox Workers (P3–P5)

**Datum:** 2026-03-21
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Plugin Sandbox Roadmap, Phase P3A/P3B + P4A/P4B + P5A/P5B

## Was wurde gemacht

### P3 — VST2 Sandbox Worker
- `plugin_workers/vst2_worker.py` (**NEU**): Lädt VST2 via Vst2Fx/Vst2InstrumentEngine
- FX-Mode: process_inplace Audio-Loop
- Instrument-Mode: note_on/off MIDI IPC → pull() Audio-Output
- State: get_state/load_state via Base64 IPC
- Parameter: set_param IPC → set_parameter()

### P4 — LV2 + LADSPA Sandbox Worker
- `plugin_workers/lv2_ladspa_worker.py` (**NEU**): Shared Worker für beide Formate
- LV2: Lv2Fx via lilv, full state save/restore
- LADSPA: LadspaFx via ctypes, parameter-snapshot als JSON/Base64 (kein nativer State)
- Beide: process_inplace Audio-Loop, set_param IPC

### P5 — CLAP Sandbox Worker
- `plugin_workers/clap_worker.py` (**NEU**): Lädt CLAP via clap_host.py
- FX + Instrument Modes (ClapInstrumentEngine für Synths)
- MIDI IPC: note_on/off/batch
- State + Params via IPC
- Editor: show/hide_editor IPC

### Routing in SandboxProcessManager
- Alle 5 Formate (vst3, vst2, lv2, ladspa, clap) werden automatisch
  zum richtigen format-spezifischen Worker geroutet
- Fallback auf generischen Worker wenn Import fehlschlägt

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/plugin_workers/vst2_worker.py | **NEU**: VST2 Worker |
| pydaw/plugin_workers/lv2_ladspa_worker.py | **NEU**: LV2+LADSPA Worker |
| pydaw/plugin_workers/clap_worker.py | **NEU**: CLAP Worker |
| pydaw/services/sandbox_process_manager.py | 5-Format-Routing |
| VERSION | 0.0.20.706 |
| pydaw/version.py | 0.0.20.706 |

## Was als nächstes zu tun ist
- Phase P7 (OPTIONAL) — Rust Native Plugin Hosting
- Rust Audio Pipeline: RA1–RA5
- VST2 GUI (X11 Window Embedding) — zurückgestellt
- LV2 eigene URID Map — zurückgestellt
- CLAP Window Embedding — zurückgestellt

## Bekannte Probleme
- VST2 GUI (effEditOpen) in Worker noch nicht implementiert (X11 Embedding nötig)
- LV2 Worker nutzt Main-Prozess URID Map — könnte bei manchen Plugins Probleme geben
- CLAP ClapAudioFxWidget ist ein QWidget — headless FX braucht ClapPluginInstance
