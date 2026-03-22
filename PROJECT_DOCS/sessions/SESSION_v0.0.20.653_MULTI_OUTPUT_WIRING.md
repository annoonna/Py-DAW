# Session Log — v0.0.20.653

**Datum:** 2026-03-20
**Kollege:** Claude Opus 4.6
**Arbeitspaket:** AP4 Phase 4B (CLAP Cleanup) + AP5 Phase 5C (Multi-Output Wiring)
**Aufgabe:** CLAP Unified Presets + Multi-Output Plugin Wiring im AudioCallback

## Was wurde erledigt

### CLAP → Unified PresetBrowserWidget
- Alten v569 Preset-Scan-Timer entfernt (Unified Widget macht eigenen Refresh)
- Undo-Notify in CLAP `_flush_to_project()` integriert
- Legacy `_preset_combo` bleibt als Hidden-Widget (AttributeError-Schutz)

### Multi-Output Plugin Wiring (Kern-Feature)
- `HybridAudioCallback`:
  - `_plugin_output_map` Slot + Init (parent_tid → {out_idx: child_tid})
  - `set_plugin_output_map()` Atomic Setter
  - `_mix_source_to_track()` — extrahierter Helper für FX→Meter→Vol/Pan→Mix Pipeline
  - `render_for_jack()` Step 8: Multi-Output Split-Routing (Stereo-Paare per Output-Index)
- `HybridEngineBridge.set_plugin_output_map()` — GUI→Audio Thread Forwarding
- `AudioEngine.rebuild_fx_maps()`:
  - Neuer Block: Baut `po_map` aus Track.plugin_output_routing + plugin_output_count
  - Pushed an Bridge
  - Taggt Pull-Sources mit `_pydaw_output_count`
- VST3 Instrument Pull-Sources: `_pydaw_output_count = 1` Default bei Registrierung

## Geänderte Dateien
- `pydaw/audio/hybrid_engine.py` — Multi-Output Wiring (Slot, Setter, Helper, Pull-Loop)
- `pydaw/audio/audio_engine.py` — rebuild_fx_maps plugin_output_map Builder + Tagging
- `pydaw/ui/fx_device_widgets.py` — CLAP Preset Timer entfernt, Undo-Notify
- `VERSION` → 0.0.20.653
- `pydaw/version.py` → 0.0.20.653
- `PROJECT_DOCS/ROADMAP_MASTER_PLAN.md` — Version-Stamp
- `PROJECT_DOCS/progress/TODO.md` — v653 Eintrag
- `PROJECT_DOCS/progress/DONE.md` — v653 Eintrag
- `CHANGELOG_v0.0.20.653_MULTI_OUTPUT_WIRING.md`

## Nächste Schritte
- **AP7 Phase 7A — Advanced Sampler**: Multi-Sample Mapping Editor
  - Sampler-Engine muss `pull()` mit (frames, 2*N) Buffer liefern für Multi-Output
  - `_pydaw_output_count` bei Sampler-Registration setzen
- Sounddevice-Callback (`_process`) ebenfalls Multi-Output-fähig machen (optional, JACK-first)
- **AP10 Phase 10C**: `render_offline` mit `include_fx=True` (DAWproject-Vorbereitung)

## Offene Fragen an den Auftraggeber
- Soll der Sounddevice-Callback (`_process` in HybridAudioCallback) ebenfalls Multi-Output bekommen, oder reicht JACK-only?
- Für AP7: Soll der Pro Drum Machine als Erster Multi-Output bekommen (1 Output pro Pad), oder der Pro Audio Sampler?
