# Session Log — v0.0.20.435 RT Store Overwrite Fix

**Datum**: 2026-03-12
**Autor**: Claude Opus 4.6

## Problem
Gain-Automation machte Sound extrem laut statt leise.
_mirror_to_rt_store() überschrieb den korrekten linear-Wert mit dem rohen dB-Wert.

## Fix
`tick()` + `clear_automation_values()`: Skip _mirror_to_rt_store wenn param._listeners existieren.

## Geänderte Dateien
- `pydaw/audio/automatable_parameter.py` — 2 Guard-Zeilen
