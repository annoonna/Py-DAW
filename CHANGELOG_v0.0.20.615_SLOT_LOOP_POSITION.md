# CHANGELOG v0.0.20.615 — Launcher Slot Loop-Position Fix

**Datum:** 2026-03-19
**Autor:** Claude Opus 4.6
**Typ:** Bugfix (Loop-Position-Anzeige im Slot)

---

## Problem

Slot-Button im Clip Launcher zeigte "0.0 Bar" statt der tatsächlichen
Loop-Position (z.B. "1.3 Bar"). Der Text aktualisierte sich nicht
während des Playbacks.

## Root Cause

`_get_loop_position_text()` griff unsicher direkt auf `playback._voices`
zu (ohne Lock, race condition möglich). Außerdem berechnete es die Position
fehlerhaft — `cur - voice_start` konnte 0 ergeben wenn Timing ungünstig.

## Fix

Ersetzt durch `get_runtime_snapshot()` — den thread-sicheren Snapshot
aus Phase B des Dual-Clock-Systems:

```python
# VORHER (Bug — unsicherer direkter Zugriff):
voices = getattr(playback, '_voices', {})
voice = voices.get(str(slot_key))
voice_start = float(getattr(voice, 'start_beat', 0.0))
local = cur - voice_start
pos_in_loop = ls + (local % span)

# NACHHER (Fix — thread-sicherer Snapshot):
snap = playback.get_runtime_snapshot(str(slot_key))
pos_in_loop = snap.local_beat - snap.loop_start_beats
```

Der Snapshot berechnet `local_beat` bereits korrekt unter Lock. Kürzer,
sicherer, und nutzt die Dual-Clock-Infrastruktur aus v612.

## Geänderte Datei

| Datei | Änderung |
|---|---|
| `pydaw/ui/clip_launcher.py` | `_get_loop_position_text()` auf Snapshot umgestellt (-20/+12 Zeilen) |
