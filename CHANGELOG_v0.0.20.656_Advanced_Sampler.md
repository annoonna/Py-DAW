# CHANGELOG v0.0.20.656 — Advanced Multi-Sample Sampler + Drum Rack

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** AP7, Phase 7A (Advanced Sampler) + Phase 7B (Drum Rack)

## Was wurde gemacht

### Neues Plugin: Advanced Multi-Sample Sampler (AP7 Phase 7A — KOMPLETT)
Komplettes Multi-Sample-System mit polyphonem Engine, visuellem Zone-Editor und Auto-Mapping.

**Datenmodell (multisample_model.py):**
- `SampleZone`: Key×Velocity Mapping mit per-Zone DSP (Filter, ADSR, LFO, Mod-Matrix)
- `MultiSampleMap`: Zone-Verwaltung mit Round-Robin-Logik
- `LoopPoints`, `ZoneEnvelope`, `ZoneFilter`, `ZoneLFO`, `ModulationSlot`: Vollständige DSP-Dataclasses
- MIDI-Note-Utilities (deutsch/englisch), Farb-Palette
- Vollständige JSON-Serialisierung (to_dict/from_dict)

**Polyphoner Engine (multisample_engine.py):**
- `MultiSampleEngine`: 32-Voice Polyphonie
- Per-Voice ADSR Envelope State Machine (Attack/Hold/Decay/Sustain/Release)
- Per-Voice LFO (Sine/Triangle/Square/Saw/Random)
- Per-Voice Biquad Filter (LP/HP/BP) mit Envelope-Modulation
- 4-Slot Modulation Matrix: 7 Sources × 4 Destinations
- Voice Allocation mit Voice-Stealing
- Sample-Cache (Load-once, play-many)
- Thread-safe pull(frames, sr) API

**Visual Zone Editor (multisample_widget.py):**
- `ZoneMapCanvas`: 2D Key×Velocity Grid mit farbigen Zone-Rechtecken
- Klick-Selektion, Drag-Resize (Kanten), Mouse-Wheel Zoom
- Root-Note Marker pro Zone
- Context-Menu: Add/Duplicate/Delete Zone
- Drag&Drop von Audio-Dateien direkt auf Grid
- `ZoneInspector`: 5-Tab Inspektor (Map/Env/Filter/Mod/Sample)
- `MultiSampleEditorWidget`: Toolbar + Canvas + Inspector mit Splitter

**Auto-Mapping (auto_mapping.py):**
- Chromatisches Mapping (Filename-Pattern: C4.wav, note_60.wav)
- GM Drum Mapping (Keyword-Erkennung: kick, snare, hat, etc.)
- Velocity-Layer Mapping (pp/p/mf/f/ff Erkennung)
- Round-Robin Mapping
- Overlap-Resolution

### Drum Rack Erweiterung (AP7 Phase 7B — KOMPLETT)

**Choke Groups (drum_engine.py):**
- `DrumSlotState.choke_group`: 0 = off, 1-8 = Mutual-Exclusion-Gruppe
- Bei Trigger: alle anderen Slots derselben Choke-Gruppe werden gesilenced
- Klassischer Anwendungsfall: Hi-Hat Open + Closed in Gruppe 1
- Serialisierung in export_state/import_state

**Pad-Bank Navigation (drum_widget.py):**
- 4 Banks (A/B/C/D) × 16 Pads = 64 Pads total
- Bank-Buttons über dem Pad-Grid
- `expand_slots()` im Engine: Safe-Expand (nur hinzufügen, nie löschen)
- Bank-aware _select_slot, _preview_slot, _on_pad_sample_dropped, _update_pad_text

**Choke Group UI (drum_widget.py):**
- QSpinBox im Slot-Editor (0-8)
- Sync in _refresh_slot_editor
- Persisted via instrument_state

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw/plugins/sampler/multisample_model.py | **NEU** — Datenmodell |
| pydaw/plugins/sampler/multisample_engine.py | **NEU** — Polyphoner Engine |
| pydaw/plugins/sampler/multisample_widget.py | **NEU** — Visual Zone Editor |
| pydaw/plugins/sampler/auto_mapping.py | **NEU** — Auto-Mapping |
| pydaw/plugins/sampler/__init__.py | Neue Exports hinzugefügt |
| pydaw/plugins/registry.py | Advanced Sampler registriert |
| pydaw/plugins/drum_machine/drum_engine.py | Choke Groups + expand_slots() |
| pydaw/plugins/drum_machine/drum_widget.py | Choke-SpinBox + Pad-Bank-Nav |
| VERSION | 0.0.20.656 |
| pydaw/version.py | 0.0.20.656 |

## Was als nächstes zu tun ist
- AP7 Phase 7C: Wavetable-Erweiterung für AETERNA
- AP10 Phase 10C: DAWproject Roundtrip
- AP1 Phase 1C: Rust Plugin-Hosting (VST3/CLAP)

## Bekannte Probleme / Offene Fragen
- Keine — alle Features kompilieren fehlerfrei, bestehender Code unverändert
