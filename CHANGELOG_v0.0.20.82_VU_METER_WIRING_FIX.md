# CHANGELOG v0.0.20.82 — Hotfix: VU-Meter Wiring Regression

## Fix
- **Mixer VU-Meter (Tracks)** wieder korrekt verdrahtet.

## Ursache
- Regression in `pydaw/audio/hybrid_engine.py`:
  - `HybridAudioCallback.set_track_index_map()` war leer.
  - Track-ID→Index Mapping wurde versehentlich in `set_bypassed_track_ids()` verschoben.
  - Dadurch wurden pro-Track Peaks/Direct-Peaks nicht mehr geschrieben.

## Geändert
- `pydaw/audio/hybrid_engine.py`

