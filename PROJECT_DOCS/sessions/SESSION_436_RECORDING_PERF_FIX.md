# Session Log — v0.0.20.436 Recording Performance Fix

**Datum**: 2026-03-12 | **Autor**: Claude Opus 4.6

## Problem
Audio stotterte massiv während Automation-Recording.
sort_points() O(n log n) + emit/repaint + legacy write — alles pro CC.

## Fix
- sort_points() entfernt (beats monoton steigend)
- lane_data_changed throttled auf 8 Hz
- Legacy store write deferred to save

## Geänderte Dateien
- `pydaw/audio/automatable_parameter.py` — _write_cc_automation + _flush_cc_ui
- `pydaw/services/midi_mapping_service.py` — _write_automation_point
