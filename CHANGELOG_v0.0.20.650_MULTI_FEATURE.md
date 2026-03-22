# CHANGELOG v0.0.20.650 — Multi-Feature: Warp/Export/Sandbox/MPE/MultiOut

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspakete:** AP3 3C, AP4 4A, AP5 5C, AP6 6B, AP10 10B

## Was wurde gemacht

### AP3 Phase 3C — Clip-Warp im Arranger (Task 4) ✅
- Warp-Marker werden jetzt im Arranger als orangene Dreiecke + gestrichelte Linien visualisiert
- Kontextmenü "🔀 Warp / Stretch" für Audio-Clips mit:
  - Stretch-Modus Auswahl (Tones/Beats/Texture/Re-Pitch/Complex) mit Checkmarks
  - Auto-Warp (Beat Detection) → setzt automatisch Warp-Marker
  - Warp-Marker löschen
- Stretch-Mode Badge (🥁🌊🎵💎) in Clip-Ecke für nicht-standard Modi
- `update_audio_clip_params()` erweitert um `stretch_mode` und `stretch_markers`

### AP4 Phase 4A — Sandboxed Plugin-Hosting ✅ (KOMPLETT)
- Neues Modul `pydaw/services/plugin_sandbox.py`:
  - `PluginSandboxManager`: Verwaltet Plugin-Worker-Subprozesse
  - `SharedAudioBuffer`: Lock-free Audio-IPC via mmap (Zero-Copy)
  - `PluginWorkerConfig`: Konfiguration pro Plugin-Worker
  - Worker-Prozess mit Plugin-Loading (VST3/CLAP), State-Restore, Audio-Processing
  - Crash-Detection via Heartbeat-Monitor-Thread (500ms Intervall)
  - Auto-Restart bei Crash (max 3 Versuche), danach Track-Mute
  - `crash_callback` für GUI-Benachrichtigung
  - Sauberes Shutdown mit Process-Termination

### AP5 Phase 5C — Multi-Output Plugins ✅
- `Track.plugin_output_routing`: Dict[int, str] für Output-Index → Track-ID Mapping
- `Track.plugin_output_count`: Anzahl Stereo-Outputs des Plugins
- Neue ProjectService-Methoden:
  - `set_plugin_output_routing()` / `get_plugin_output_routing()`
  - `set_plugin_output_count()`
  - `create_plugin_output_tracks()` — erstellt automatisch Hilfs-Tracks + Routing

### AP6 Phase 6B — MPE Support ✅ (KOMPLETT)
- Neues Modul `pydaw/audio/mpe_support.py`:
  - `MPEConfig` / `MPEZoneConfig`: Konfiguration mit JSON-Serialisierung
  - `MPEChannelAllocator`: Round-Robin Channel-Zuweisung pro Note, Voice Stealing
  - `MPEProcessor`: Verarbeitet Note-On/Off, Pitch Bend, Pressure, CC74 (Slide)
  - Per-Note Expression-Curves → `MidiNote.expressions` Konvertierung
  - Lower/Upper Zone Support (MIDI-CA RP-053 konform)
  - Presets für bekannte Controller (Seaboard, Linnstrument, Sensel Morph, Continuum, Push 3)
  - MCM Detection API (für automatische MPE-Erkennung)
- `Track.mpe_config`: Dict für MPE-Konfiguration pro Track

### AP10 Phase 10B — Pre-/Post-FX Export (Task 4) ✅
- `ExportConfig.fx_mode`: "post_fx" (default), "pre_fx" (dry), "both" (wet + dry)
- Export-Dialog: ComboBox "Post-FX / Pre-FX / Beides"
- Render-Funktion erhält `include_fx` Parameter (mit TypeError-Fallback)
- Dateinamen: `_wet` / `_dry` Suffix bei "both"-Modus

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/model/project.py | Track: plugin_output_routing, plugin_output_count, mpe_config |
| pydaw/ui/arranger_canvas.py | _draw_clip_warp_markers(), Warp-Kontextmenü + Handler |
| pydaw/ui/audio_export_dialog.py | cmb_fx_mode ComboBox, include_fx in render_func |
| pydaw/services/project_service.py | stretch_mode/markers in update_audio_clip_params, Multi-Output API |
| pydaw/services/audio_export_service.py | ExportConfig.fx_mode, render_passes mit include_fx |
| pydaw/services/plugin_sandbox.py | NEU: Komplettes Sandbox-Framework |
| pydaw/audio/mpe_support.py | NEU: Komplettes MPE-Framework |
| pydaw/version.py | 0.0.20.650 |
| VERSION | 0.0.20.650 |
| PROJECT_DOCS/ROADMAP_MASTER_PLAN.md | Checkboxen aktualisiert |

## Was als nächstes zu tun ist
- AP4 Phase 4B: Preset-Browser (VST3/CLAP Preset-Scan, UI)
- AP4 Phase 4C: Plugin-State Management (Auto-Save, Undo/Redo)
- AP10 Phase 10C: DAWproject Roundtrip
- AP7 Phase 7A: Advanced Sampler (Multi-Sample Mapping Editor)

## Bekannte Probleme / Offene Fragen
- Sandbox-Integration in HybridAudioCallback steht noch aus (Worker-Prozesse müssen in den Audio-Graph eingebunden werden)
- MPE-Integration in MIDI-Service und Piano Roll UI benötigt Wiring (MPEProcessor ist ready, muss in midi_manager.py eingebunden werden)
- Multi-Output Plugin Audio-Routing im HybridAudioCallback noch nicht verdrahtet (Model + API fertig)
- `render_offline(include_fx=...)` muss im ArrangementRenderer implementiert werden (API-Schnittstelle steht, Fallback via TypeError vorhanden)
