# CHANGELOG v0.0.20.676 — Phase R6B: MultiSample Instrument

**Datum:** 2026-03-20
**Autor:** Claude Opus 4.6
**Arbeitspaket:** Rust DSP Migration, Phase R6B

## Was wurde gemacht

### Neues Rust-Modul: `instruments/multisample.rs` (~1050 Zeilen)
- **SampleZone**: Zone-Mapping mit Key Range × Velocity Range, Root Note, Gain, Pan, Tuning
- **MultiSampleMap**: Zone-Verwaltung mit Lookup by (note, velocity), Pre-allokiert (max 256 Zones)
- **Round-Robin**: rr_group Counter pro Trigger-Gruppe (max 32 Gruppen), zyklische Auswahl
- **Per-Zone Filter**: Biquad (LP/HP/BP) mit Filter-Envelope-Modulation
- **Per-Zone ADSR**: Separate Amp- und Filter-Envelopes (AHDSR params)
- **Per-Zone LFO**: 2 LFOs pro Zone (Sine, Triangle, Square, Saw, S&H)
- **Modulation Matrix**: 4 Mod-Slots pro Zone (Source → Destination mit Amount)
  - Sources: LFO1, LFO2, EnvAmp, EnvFilter, Velocity, KeyTrack
  - Destinations: Pitch, FilterCutoff, Amp, Pan
- **Auto-Mapping**: 3 Modi — Chromatic, Drum (GM-Style), VelocityLayer
- **Voice Pool**: 64 polyphon, Pre-allokiert, Voice-Stealing (Free→Releasing→Oldest)
- **Lock-free MIDI/Commands**: Bounded crossbeam channels (256 MIDI, 64 Cmd)
- **InstrumentNode Trait**: Vollständig implementiert, registriert in Factory
- **18 Unit-Tests**: Creation, Silence, Play, Key/Vel-Filtering, RR, NoteOff, AllSoundOff, ClearZones, AutoMap (3 Modi), Filter/ModSource parsing, Polyphonie, Master Gain

### IPC Commands erweitert (`ipc.rs`)
- `AddSampleZone`: Zone mit WAV, Key/Vel-Range, Root, Gain, Pan, Tune, RR-Group
- `RemoveSampleZone`, `ClearAllZones`
- `SetZoneFilter`: Filter-Typ, Cutoff, Resonance, Env-Amount
- `SetZoneEnvelope`: Amp oder Filter ADSR pro Zone
- `SetZoneLfo`: Rate + Shape pro Zone (2 LFOs)
- `SetZoneModSlot`: Source/Destination/Amount pro Mod-Slot
- `AutoMapZones`: Batch-Auto-Mapping (Chromatic/Drum/VelocityLayer)

### Python Bridge erweitert (`rust_engine_bridge.py`)
- 12 neue Methoden: load_instrument, unload_instrument, load_sample,
  add_sample_zone, remove_sample_zone, clear_all_zones, set_zone_filter,
  set_zone_envelope, set_zone_lfo, set_zone_mod_slot, auto_map_zones

### instruments/mod.rs
- MultiSample-Modul registriert + Re-Export
- InstrumentType::MultiSample in Factory (`create()`)
- Neuer Test: test_instrument_type_create_multisample

## Geänderte Dateien
| Datei | Änderung |
|---|---|
| pydaw_engine/src/instruments/multisample.rs | **NEU** — Komplette MultiSample-Engine (~1050 Z.) |
| pydaw_engine/src/instruments/mod.rs | MultiSample registriert, Factory, Test |
| pydaw_engine/src/ipc.rs | 8 neue IPC Commands für MultiSample |
| pydaw/services/rust_engine_bridge.py | 12 neue Bridge-Methoden |
| VERSION, pydaw/version.py | 675 → 676 |

## Was als nächstes zu tun ist
- Phase R7A — DrumMachine: 128 Pad-Slots, Choke Groups, GM Drum Map
- (oder alternativ) Phase R6B IPC-Dispatch: Engine.rs muss die neuen Commands an MultiSampleInstrument weiterleiten

## Bekannte Probleme / Offene Fragen
- Cargo nicht in Build-Umgebung verfügbar → Rust-Kompilierung konnte nicht verifiziert werden (Bracket-Balance und Pattern-Konsistenz manuell geprüft)
- Engine.rs Command-Dispatch für neue MultiSample-Commands muss noch implementiert werden (Phase R7 oder dedizierter Folge-Task)
